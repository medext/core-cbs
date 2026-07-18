"""Tenant directory: validated lookup of tenants and their database aliases.

Two implementations, selected by the deployment profile:
- ``control``  — SaaS: reads the control-plane registry and registers the tenant's
  database alias at runtime (ADR-0005).
- ``static``   — on-premise: exactly one tenant from environment configuration; the
  control-plane runtime is absent.
"""

import uuid
from typing import Protocol

import environ
from django.conf import settings
from django.db import connections

from next_core.tenancy.context import TenantContext
from next_core.tenancy.exceptions import TenantResolutionError
from next_core.tenancy.router import TENANT_ALIAS_PREFIX


class TenantDirectory(Protocol):
    def lookup(self, slug: str) -> TenantContext:
        """Return the context for an ACTIVE tenant or raise TenantResolutionError."""
        ...

    def all_active(self) -> list[TenantContext]:
        """All tenants eligible for fan-out operations (migrations, sweeps)."""
        ...


def register_tenant_alias(alias: str, dsn: str) -> None:
    """Make a tenant database reachable under ``alias`` for this process.

    Idempotent; used by the control directory and the migration fan-out command.
    """
    if not alias.startswith(TENANT_ALIAS_PREFIX):
        raise TenantResolutionError(f"'{alias}' is not a tenant database alias.")
    if alias in connections.databases:
        return
    config = environ.Env.db_url_config(dsn)
    if not str(config.get("ENGINE", "")).endswith("postgresql"):
        raise TenantResolutionError("Tenant databases must be PostgreSQL (ADR-0003).")
    config.setdefault("ATOMIC_REQUESTS", False)
    config.setdefault("AUTOCOMMIT", True)
    config.setdefault("CONN_MAX_AGE", 60)
    config.setdefault("CONN_HEALTH_CHECKS", True)
    config.setdefault("OPTIONS", {})
    config.setdefault("TIME_ZONE", None)
    connections.databases[alias] = config


class ControlPlaneDirectory:
    """SaaS: tenants come from the control-plane registry (control database)."""

    def lookup(self, slug: str) -> TenantContext:
        from next_core.control_plane.models import Tenant, TenantStatus

        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise TenantResolutionError(f"Unknown tenant '{slug}'.") from exc
        if tenant.status != TenantStatus.ACTIVE:
            raise TenantResolutionError(f"Tenant '{slug}' is not active ({tenant.status}).")
        register_tenant_alias(tenant.db_alias, tenant.database_dsn)
        return TenantContext(tenant_id=tenant.id, slug=tenant.slug, db_alias=tenant.db_alias)

    def all_active(self) -> list[TenantContext]:
        from next_core.control_plane.models import Tenant, TenantStatus

        contexts: list[TenantContext] = []
        for tenant in Tenant.objects.filter(status=TenantStatus.ACTIVE).order_by("slug"):
            register_tenant_alias(tenant.db_alias, tenant.database_dsn)
            contexts.append(
                TenantContext(tenant_id=tenant.id, slug=tenant.slug, db_alias=tenant.db_alias)
            )
        return contexts


class StaticDirectory:
    """On-premise: the single tenant is defined by configuration, not a registry."""

    def _static_context(self) -> TenantContext:
        tenant_id = getattr(settings, "NEXT_CORE_TENANT_ID", "")
        slug = getattr(settings, "NEXT_CORE_TENANT_SLUG", "")
        alias = getattr(settings, "NEXT_CORE_TENANT_DB_ALIAS", "")
        if not (tenant_id and slug and alias):
            raise TenantResolutionError(
                "On-premise tenant configuration missing (NEXT_CORE_TENANT_ID / _SLUG / _DB_ALIAS)."
            )
        return TenantContext(tenant_id=uuid.UUID(tenant_id), slug=slug, db_alias=alias)

    def lookup(self, slug: str) -> TenantContext:
        ctx = self._static_context()
        if slug != ctx.slug:
            raise TenantResolutionError(f"Unknown tenant '{slug}'.")
        return ctx

    def all_active(self) -> list[TenantContext]:
        return [self._static_context()]


def get_directory() -> TenantDirectory:
    kind = getattr(settings, "NEXT_CORE_TENANT_DIRECTORY", "control")
    if kind == "static":
        return StaticDirectory()
    if kind == "control":
        return ControlPlaneDirectory()
    raise TenantResolutionError(f"Unknown tenant directory kind '{kind}'.")
