"""Sets the request's tenant context - this MUST be a plain ASGI middleware,
not a FastAPI/Starlette dependency.

Why: FastAPI dispatches every sync dependency (get_current_user included) and
every sync path-operation function through *separate* `run_in_threadpool`
calls. Each of those calls takes its own snapshot of the current context via
`contextvars.copy_context()` - a ContextVar mutation made inside one sync
dependency's threadpool call is invisible to the next one, including the
actual endpoint body. So setting the tenant ContextVar from inside
`get_current_user` (a dependency) never actually reaches the query code that
needs it.

Middleware runs once, in the request's own coroutine, *before* any of that
threadpool dispatching begins - so a ContextVar set here is present in the
snapshot every later threadpool call takes. This is the only place in the
stack where the mutation reliably propagates for both sync and async routes.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.security import decode_access_token
from app.core.tenant_context import set_authenticated_no_tenant, set_current_tenant_id

_ADMIN_PATH_PREFIX = "/api/admin"


class TenantContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            self._set_tenant_context(scope)
        await self.app(scope, receive, send)

    @staticmethod
    def _set_tenant_context(scope: Scope) -> None:
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if not auth.lower().startswith("bearer "):
            return
        payload = decode_access_token(auth[7:])
        if not payload or "tenant_id" not in payload:
            return

        tenant_id = payload["tenant_id"]
        if tenant_id is not None:
            set_current_tenant_id(tenant_id)
            return

        # tenant_id is None only for Super Admins (see User.tenant_id). Only
        # their own /api/admin/* namespace gets genuinely unfiltered access;
        # anywhere else, default-deny (a Super Admin token hitting an
        # ordinary endpoint sees nothing, not everything).
        path = scope.get("path", "")
        if payload.get("role") == "super_admin" and path.startswith(_ADMIN_PATH_PREFIX):
            set_current_tenant_id(None)
        else:
            set_authenticated_no_tenant()
