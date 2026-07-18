"""Tenant resolution at the boundary: hard failures, never a fallback (gate item)."""

import json

import pytest
from django.test import Client

from next_core.control_plane.models import Tenant, TenantStatus

pytestmark = pytest.mark.integration


def _get(client: Client, **kwargs: str) -> tuple[int, dict[str, object]]:
    response = client.get("/api/v1/audit/events", headers=kwargs or None)
    return response.status_code, json.loads(response.content)


@pytest.mark.django_db
def test_missing_tenant_header_is_a_hard_400() -> None:
    status, body = _get(Client())
    assert status == 400
    assert body["code"] == "TENANT_RESOLUTION_FAILED"
    assert body["retryable"] is False


@pytest.mark.django_db
def test_malformed_tenant_slug_is_rejected() -> None:
    status, body = _get(Client(), **{"X-Tenant-ID": "Robert'); DROP TABLE--"})
    assert status == 400
    assert body["code"] == "TENANT_RESOLUTION_FAILED"


@pytest.mark.django_db
def test_unknown_tenant_is_rejected() -> None:
    status, body = _get(Client(), **{"X-Tenant-ID": "ghost"})
    assert status == 400
    assert body["code"] == "TENANT_RESOLUTION_FAILED"


@pytest.mark.django_db
def test_non_active_tenant_is_rejected(tenants: dict[str, Tenant]) -> None:
    Tenant.objects.filter(slug="alpha").update(status=TenantStatus.SUSPENDED)
    status, body = _get(Client(), **{"X-Tenant-ID": "alpha"})
    assert status == 400
    assert body["code"] == "TENANT_RESOLUTION_FAILED"


@pytest.mark.django_db
def test_health_endpoints_are_exempt_from_tenant_scope() -> None:
    assert Client().get("/health/live").status_code == 200
