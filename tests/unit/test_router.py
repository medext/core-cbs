"""Database router: data-plane queries REQUIRE a tenant context; migrations stay in
their plane. No default tenant, ever (invariant 14 foundation)."""

import uuid

import pytest

from next_core.audit.models import AuditEvent
from next_core.control_plane.models import Tenant
from next_core.tenancy.context import TenantContext, tenant_context
from next_core.tenancy.exceptions import TenantContextMissingError
from next_core.tenancy.router import TenantDatabaseRouter

ROUTER = TenantDatabaseRouter()
ALPHA = TenantContext(tenant_id=uuid.uuid4(), slug="alpha", db_alias="tenant_alpha")


def test_data_plane_read_without_context_raises() -> None:
    with pytest.raises(TenantContextMissingError):
        ROUTER.db_for_read(AuditEvent)


def test_data_plane_write_without_context_raises() -> None:
    with pytest.raises(TenantContextMissingError):
        ROUTER.db_for_write(AuditEvent)


def test_data_plane_routes_to_current_tenant_db() -> None:
    with tenant_context(ALPHA):
        assert ROUTER.db_for_read(AuditEvent) == "tenant_alpha"
        assert ROUTER.db_for_write(AuditEvent) == "tenant_alpha"


def test_control_plane_routes_to_control_db_without_context() -> None:
    assert ROUTER.db_for_read(Tenant) == "default"
    assert ROUTER.db_for_write(Tenant) == "default"


@pytest.mark.parametrize(
    ("db", "app", "allowed"),
    [
        ("default", "audit", False),  # data-plane tables never in the control DB
        ("tenant_alpha", "audit", True),
        ("default", "control_plane", True),
        ("tenant_alpha", "control_plane", False),  # registry never in tenant DBs
        ("default", "auth", True),
        ("tenant_alpha", "auth", False),
    ],
)
def test_allow_migrate_keeps_planes_separate(db: str, app: str, allowed: bool) -> None:
    assert ROUTER.allow_migrate(db, app) is allowed
