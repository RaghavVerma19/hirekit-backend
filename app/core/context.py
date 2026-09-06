from contextvars import ContextVar
from typing import Optional
import uuid

# ContextVars holding the current request's tenant context
tenant_id_ctx: ContextVar[Optional[uuid.UUID]] = ContextVar("tenant_id_ctx", default=None)
tenant_slug_ctx: ContextVar[Optional[str]] = ContextVar("tenant_slug_ctx", default=None)


def set_tenant_context(tenant_id: Optional[uuid.UUID], tenant_slug: Optional[str] = None) -> None:
    """Set the active tenant context for the current async task."""
    tenant_id_ctx.set(tenant_id)
    if tenant_slug:
        tenant_slug_ctx.set(tenant_slug)


def get_current_tenant_id() -> Optional[uuid.UUID]:
    """Retrieve the active tenant ID from context."""
    return tenant_id_ctx.get()


def get_current_tenant_slug() -> Optional[str]:
    """Retrieve the active tenant slug from context."""
    return tenant_slug_ctx.get()


def clear_tenant_context() -> None:
    """Clear tenant context vars."""
    tenant_id_ctx.set(None)
    tenant_slug_ctx.set(None)
