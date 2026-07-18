"""Explicit tenant context (ADR-0005).

The context is established exactly once at a boundary (request middleware, job wrapper,
management command) and carried in a contextvar. Domain code reads it through
``current_tenant()`` — which raises if absent. There is no default tenant, ever.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import structlog

from next_core.tenancy.exceptions import TenantContextMissingError


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Validated identity of the tenant a unit of work operates for."""

    tenant_id: uuid.UUID
    slug: str
    db_alias: str


_current: ContextVar[TenantContext | None] = ContextVar("next_core_tenant", default=None)


def current_tenant() -> TenantContext:
    """Return the established tenant context, or raise — never a fallback."""
    ctx = _current.get()
    if ctx is None:
        raise TenantContextMissingError(
            "No tenant context is established for this operation. Data-plane code must run "
            "inside tenant_context(...); a fallback tenant is prohibited."
        )
    return ctx


def current_tenant_or_none() -> TenantContext | None:
    """Introspection helper for infrastructure code (router, logging). Domain code
    must use current_tenant()."""
    return _current.get()


@contextmanager
def tenant_context(ctx: TenantContext) -> Iterator[TenantContext]:
    """Establish ``ctx`` for the duration of the block. Nesting a different tenant is
    prohibited (jobs iterating tenants must exit one context before entering the next)."""
    existing = _current.get()
    if existing is not None and existing.tenant_id != ctx.tenant_id:
        raise TenantContextMissingError(
            f"Tenant context already established for '{existing.slug}'; refusing to nest "
            f"'{ctx.slug}'. Exit the current context first."
        )
    token = _current.set(ctx)
    structlog.contextvars.bind_contextvars(tenant=ctx.slug)
    try:
        yield ctx
    finally:
        _current.reset(token)
        structlog.contextvars.unbind_contextvars("tenant")
