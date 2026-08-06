"""Automatic multi-tenant row isolation.

Every table that mixes in TenantMixin (see app.models.mixins) gets its queries
transparently filtered to the current request's tenant, and new rows
transparently stamped with it - callers never pass tenant_id explicitly, and
the ~180 existing router/service call sites across the app don't change.

This is SQLAlchemy's documented "global WHERE criteria" recipe for shared-
database multi-tenancy:
https://docs.sqlalchemy.org/en/20/orm/session_events.html#adding-global-where-on-criteria

Isolation is driven by a ContextVar set once per request (see
app.api.deps.get_current_tenant), not by anything the client sends - a
tampered request body can't widen access, only the signed JWT's tenant_id can.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.models.mixins import TenantMixin

_current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> int | None:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: int | None) -> None:
    _current_tenant_id.set(tenant_id)


@contextmanager
def tenant_scope(tenant_id: int | None):
    """Run a block of code scoped to a specific tenant (or None = unfiltered).

    Used outside the request/response cycle - the scheduler, seed scripts,
    the Super Admin API - anywhere there's no JWT to derive it from.
    """
    token = _current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)


def register_tenant_isolation() -> None:
    """Call once at startup (see app.core.database) to wire the filter+stamp events."""

    @event.listens_for(Session, "do_orm_execute")
    def _filter_by_tenant(execute_state):
        if execute_state.is_column_load:
            # Refreshing a deferred/expired attribute on an already-identified,
            # already-trusted object - not a fresh query.
            return
        if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
            return
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            # No tenant in scope: Super Admin endpoints and out-of-request scripts
            # (seed, migrations) explicitly opt out by never setting one.
            return
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantMixin,
                lambda cls: cls.tenant_id == tenant_id,
                include_aliases=True,
            )
        )

    @event.listens_for(Session, "before_flush")
    def _stamp_tenant_on_insert(session, _flush_context, _instances):
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return
        for obj in session.new:
            if isinstance(obj, TenantMixin) and getattr(obj, "tenant_id", None) is None:
                obj.tenant_id = tenant_id
