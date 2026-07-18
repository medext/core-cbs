"""Database routing (ADR-0005).

- Control-plane and Django-internal models live in the control database (the ``default``
  alias in every profile).
- Data-plane models live in tenant databases (aliases prefixed ``tenant_``) and are routed
  from the established TenantContext. Without a context the router RAISES — an unscoped
  data-plane query is a defect, never silently sent to a default database.
"""

from typing import Any

from django.conf import settings
from django.db.models import Model

from next_core.tenancy.context import current_tenant

CONTROL_DB_ALIAS = "default"
TENANT_ALIAS_PREFIX = "tenant_"


def data_plane_app_labels() -> frozenset[str]:
    return frozenset(getattr(settings, "NEXT_CORE_DATA_PLANE_APPS", ("audit",)))


def is_tenant_alias(alias: str) -> bool:
    return alias.startswith(TENANT_ALIAS_PREFIX)


class TenantDatabaseRouter:
    """Routes by app label: data-plane apps → current tenant DB; everything else → control."""

    def _route(self, app_label: str) -> str:
        if app_label in data_plane_app_labels():
            return current_tenant().db_alias  # raises TenantContextMissingError when absent
        return CONTROL_DB_ALIAS

    def db_for_read(self, model: type[Model], **hints: Any) -> str:
        return self._route(model._meta.app_label)

    def db_for_write(self, model: type[Model], **hints: Any) -> str:
        return self._route(model._meta.app_label)

    def allow_relation(self, obj1: Model, obj2: Model, **hints: Any) -> bool | None:
        # Relations may exist only within one plane; cross-plane references are by ID.
        labels = data_plane_app_labels()
        return (obj1._meta.app_label in labels) == (obj2._meta.app_label in labels)

    def allow_migrate(
        self, db: str, app_label: str, model_name: str | None = None, **hints: Any
    ) -> bool:
        if app_label in data_plane_app_labels():
            return is_tenant_alias(db)
        return db == CONTROL_DB_ALIAS
