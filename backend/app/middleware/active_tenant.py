"""Request middleware that surfaces the ``X-Tenant-Id`` header to the app.

Multi-tenant switching works like this:

1. This middleware reads the ``X-Tenant-Id`` header and publishes its raw value to a
   request-scoped contextvar (:data:`REQUESTED_TENANT_ID_CTX`).
2. ``get_current_user`` (app.api.auth) reads that value, validates that the caller is a
   member of the requested tenant, and publishes the resolved id to
   :data:`ACTIVE_TENANT_ID_CTX`.
3. ``scope_current_tenant`` (app.services.tenant_scoping) scopes every query to the
   active tenant for the request.

It is a plain ASGI middleware (no base class) on purpose: awaiting the inner app inline
keeps the whole request in one coroutine, so the contextvar set here is visible to
``get_current_user`` and every endpoint. The middleware is auth-free -- it only forwards
the header so that ``get_current_user`` (which already has the user and DB session) owns
all validation. It runs for every HTTP request; non-HTTP scopes (websocket / lifespan)
pass through untouched. The contextvar is reset in ``finally`` so it never leaks across
requests even when requests share an asyncio task.
"""
from typing import Optional

from app.services.tenant_scoping import set_requested_tenant_id


def _header(scope: dict, name: str) -> Optional[str]:
    """Lowercase header lookup from the ASGI scope (version-independent)."""
    for key, value in scope.get("headers", []):
        if key.decode().lower() == name:
            return value.decode()
    return None


class ActiveTenantMiddleware:
    def __init__(self, app) -> None:
        # app is the inner ASGI callable (FastAPI app or next middleware).
        self.app = app

    async def __call__(self, scope, receive, send):
        http_scope = scope.get("type") == "http"
        if http_scope:
            raw = _header(scope, "x-tenant-id")
            set_requested_tenant_id(raw.strip() if raw else None)
        try:
            await self.app(scope, receive, send)
        finally:
            if http_scope:
                set_requested_tenant_id(None)
