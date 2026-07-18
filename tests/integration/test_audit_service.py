"""Audit foundation: emission with correlation IDs, tenant requirement, append-only."""

import pytest
import structlog

from next_core.audit.service import record_event
from next_core.control_plane.models import Tenant
from next_core.tenancy.context import TenantContext, tenant_context
from next_core.tenancy.exceptions import TenantContextMissingError
from tests.conftest import TENANT_DBS

pytestmark = pytest.mark.integration


def _ctx(tenant: Tenant) -> TenantContext:
    return TenantContext(tenant_id=tenant.id, slug=tenant.slug, db_alias=tenant.db_alias)


@pytest.mark.django_db(databases=TENANT_DBS)
def test_record_event_requires_tenant_context(tenants: dict[str, Tenant]) -> None:
    with pytest.raises(TenantContextMissingError):
        record_event(
            operation="x",
            resource_type="y",
            resource_id="z",
            actor="a",
            actor_type="SYSTEM",
        )


@pytest.mark.django_db(databases=TENANT_DBS)
def test_record_event_captures_correlation_id(tenants: dict[str, Tenant]) -> None:
    structlog.contextvars.bind_contextvars(correlation_id="req_test123")
    try:
        with tenant_context(_ctx(tenants["alpha"])):
            event = record_event(
                operation="config.change",
                resource_type="product",
                resource_id="p-1",
                actor="ops-user",
                actor_type="USER",
                payload={"before": "a", "after": "b"},
            )
    finally:
        structlog.contextvars.unbind_contextvars("correlation_id")
    assert event.correlation_id == "req_test123"
    assert event.tenant_id == tenants["alpha"].id


@pytest.mark.django_db(databases=TENANT_DBS)
def test_audit_events_are_append_only(tenants: dict[str, Tenant]) -> None:
    with tenant_context(_ctx(tenants["alpha"])):
        event = record_event(
            operation="x",
            resource_type="y",
            resource_id="z",
            actor="a",
            actor_type="SYSTEM",
        )
        event.actor = "tampered"
        with pytest.raises(TypeError, match="append-only"):
            event.save()
        with pytest.raises(TypeError, match="append-only"):
            event.delete()


@pytest.mark.django_db(databases=TENANT_DBS)
def test_oversized_payload_is_rejected(tenants: dict[str, Tenant]) -> None:
    with tenant_context(_ctx(tenants["alpha"])), pytest.raises(ValueError, match="bound"):
        record_event(
            operation="x",
            resource_type="y",
            resource_id="z",
            actor="a",
            actor_type="SYSTEM",
            payload={"blob": "x" * 20_000},
        )
