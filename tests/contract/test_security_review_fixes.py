"""Regression tests for the Phase 2 security-review findings (each maps to a finding)."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client, override_settings

from next_core.audit.models import AuditEvent
from next_core.control_plane.models import Tenant, TenantStatus
from next_core.tenancy.context import TenantContext, tenant_context
from tests.conftest import TENANT_DBS, TokenFactory

pytestmark = pytest.mark.integration

URL = "/api/v1/audit/events"


# --- HIGH-1: malformed bearer token must be 401, never 500 --------------------------------


@pytest.mark.django_db(databases=TENANT_DBS)
def test_malformed_bearer_token_is_401(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    for garbage in ("garbage-token", "a.b", "eyJhbGciOiJSUzI1NiJ9.not-json.sig"):
        response = Client().get(
            URL, headers={"X-Tenant-ID": "alpha", "Authorization": f"Bearer {garbage}"}
        )
        assert response.status_code == 401, (garbage, response.status_code)


# --- HIGH-2: startup check refuses shared-issuer multi-tenant config ----------------------


def test_system_check_flags_issuer_template_without_tenant_placeholder() -> None:
    from next_core.iam.checks import issuer_template_binds_tenant

    with override_settings(
        NEXT_CORE_TENANT_DIRECTORY="control",
        OIDC_ISSUER_TEMPLATE="https://iam.example/realms/shared",
    ):
        errors = issuer_template_binds_tenant()
        assert [e.id for e in errors] == ["next_core.E001"]

    with override_settings(
        NEXT_CORE_TENANT_DIRECTORY="control",
        OIDC_ISSUER_TEMPLATE="https://iam.example/realms/{tenant}",
    ):
        assert issuer_template_binds_tenant() == []

    # Single-tenant on-prem may legitimately use a fixed issuer.
    with override_settings(
        NEXT_CORE_TENANT_DIRECTORY="static",
        OIDC_ISSUER_TEMPLATE="https://iam.bank.internal/realms/bank",
    ):
        assert issuer_template_binds_tenant() == []


@pytest.mark.django_db
def test_manage_check_runs_the_guard() -> None:
    out = StringIO()
    call_command("check", stdout=out)  # current test settings are compliant -> no error


# --- MEDIUM-1: resolution failures do not leak tenant existence/status --------------------


@pytest.mark.django_db
def test_resolution_failure_detail_is_generic(tenants: dict[str, Tenant]) -> None:
    Tenant.objects.filter(slug="alpha").update(status=TenantStatus.SUSPENDED)
    client = Client()
    bodies = []
    for header in ({}, {"X-Tenant-ID": "ghost"}, {"X-Tenant-ID": "alpha"}):
        response = client.get(URL, headers=header or None)
        assert response.status_code == 400
        bodies.append(json.loads(response.content)["detail"])
    # All three failure modes return the exact same detail — no oracle.
    assert len(set(bodies)) == 1
    assert "SUSPENDED" not in bodies[0] and "Unknown" not in bodies[0]


# --- MEDIUM-2: bulk mutation paths on audit evidence are refused --------------------------


@pytest.mark.django_db(databases=TENANT_DBS)
def test_audit_bulk_update_and_delete_are_refused(tenants: dict[str, Tenant]) -> None:
    tenant = tenants["alpha"]
    ctx = TenantContext(tenant_id=tenant.id, slug=tenant.slug, db_alias=tenant.db_alias)
    with tenant_context(ctx):
        AuditEvent(
            tenant_id=tenant.id,
            actor="a",
            actor_type="SYSTEM",
            operation="x",
            resource_type="y",
            resource_id="z",
            correlation_id="c",
        ).save()
        with pytest.raises(TypeError, match="append-only"):
            AuditEvent.objects.filter(operation="x").update(actor="tampered")
        with pytest.raises(TypeError, match="append-only"):
            AuditEvent.objects.filter(operation="x").delete()
    # The unscoped base manager refuses bulk mutation too.
    with pytest.raises(TypeError, match="append-only"):
        AuditEvent.all_objects.using("tenant_alpha").filter(operation="x").update(actor="t")
