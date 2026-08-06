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

# Matches no real tenant (ids start at 1) - see set_authenticated_no_tenant().
_DENIED = -1


def get_current_tenant_id() -> int | None:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: int | None) -> None:
    _current_tenant_id.set(tenant_id)


def set_authenticated_no_tenant() -> None:
    """For a logged-in user who genuinely has no tenant (Super Admins - see
    User.tenant_id). Deliberately NOT the same as an unset context: this
    denies every tenant-scoped row by default (renders `tenant_id = -1`,
    which matches nothing) rather than skipping the filter, so a Super
    Admin's token can't see cross-tenant data just by hitting an ordinary
    endpoint. Only the Super Admin router explicitly opts back into
    unfiltered access via tenant_scope(None) for its own request.
    """
    _current_tenant_id.set(_DENIED)


@contextmanager
def tenant_scope(tenant_id: int | None):
    """Run a block of code scoped to a specific tenant (or None = unfiltered).

    Used outside the request/response cycle - the scheduler, seed scripts -
    and by the Super Admin API to deliberately go cross-tenant for its own
    request after require_super_admin has already verified the caller.
    """
    token = _current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)


_isolation_registered = False


def register_tenant_isolation() -> None:
    """Call once at process startup (app.main, and standalone scripts like
    app.seed that use the DB outside the FastAPI app) to wire the filter+
    stamp events. Idempotent - event.listens_for would otherwise double-attach
    if called more than once in the same process (e.g. tests re-importing).
    """
    global _isolation_registered
    if _isolation_registered:
        return
    _isolation_registered = True

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
