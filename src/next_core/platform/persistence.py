"""Persistence primitives shared by data-plane contexts (no business policy).

- ``TenantScopedManager``: every queryset carries an explicit ``tenant_id`` predicate for
  the established tenant context (belt) on top of tenant-database routing (braces). Without
  a context it raises — there is no unscoped data-plane access path for domain code.
- ``AppendOnlyQuerySet`` / ``AppendOnlyModel``: refuse updates and deletes at the model
  layer; financial tables additionally carry database triggers (the authority).
"""

from typing import Any, TypeVar

from django.db import models

from next_core.tenancy.context import current_tenant

M = TypeVar("M", bound=models.Model)


class TenantScopedManager(models.Manager[M]):
    def get_queryset(self) -> models.QuerySet[M]:
        return super().get_queryset().filter(tenant_id=current_tenant().tenant_id)


class AppendOnlyQuerySet(models.QuerySet[M]):
    def update(self, **kwargs: Any) -> int:
        raise TypeError(f"{self.model.__name__} is append-only; updates are prohibited.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError(f"{self.model.__name__} is append-only; deletes are prohibited.")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        raise TypeError(f"{self.model.__name__} is append-only; updates are prohibited.")


class AppendOnlyManager(models.Manager[M]):
    """Unscoped append-only manager (framework base manager + per-database verification)."""

    def get_queryset(self) -> AppendOnlyQuerySet[M]:
        return AppendOnlyQuerySet(self.model, using=self._db)


class TenantScopedAppendOnlyManager(AppendOnlyManager[M]):
    def get_queryset(self) -> AppendOnlyQuerySet[M]:
        qs = super().get_queryset()
        return qs.filter(tenant_id=current_tenant().tenant_id)


class AppendOnlyModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise TypeError(f"{type(self).__name__} is append-only; updates are prohibited.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError(f"{type(self).__name__} is append-only; deletes are prohibited.")


def tenant_id() -> Any:
    """The current tenant id (raises without context)."""
    return current_tenant().tenant_id
