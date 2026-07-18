"""Cross-tenant isolation — the Phase 2 gate's central suite.

Authenticated as tenant alpha, every path to tenant beta's data must fail safely with no
existence leak. Data written under each tenant context must land only in that tenant's
database (verified with unscoped per-database queries).
"""

import json
import uuid

import pytest
from django.test import Client

from next_core.audit.models import AuditEvent
from next_core.control_plane.models import Tenant
from next_core.tenancy.context import TenantContext, tenant_context
from tests.conftest import TENANT_DBS, TokenFactory

pytestmark = pytest.mark.integration


def _ctx(tenant: Tenant) -> TenantContext:
    return TenantContext(tenant_id=tenant.id, slug=tenant.slug, db_alias=tenant.db_alias)


def _seed_events(tenants: dict[str, Tenant]) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for slug, tenant in tenants.items():
        with tenant_context(_ctx(tenant)):
            event = AuditEvent(
                tenant_id=tenant.id,
                actor=f"seed-{slug}",
                actor_type="SYSTEM",
                operation=f"seed.{slug}",
                resource_type="seed",
                resource_id=slug,
                correlation_id=f"corr-{slug}",
            )
            event.save()
            ids[slug] = event.id
    return ids


@pytest.mark.django_db(databases=TENANT_DBS)
def test_tenant_a_sees_only_its_own_events(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    ids = _seed_events(tenants)
    token = token_factory.mint("alpha")
    response = Client().get(
        "/api/v1/audit/events",
        headers={"X-Tenant-ID": "alpha", "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.content
    body = json.loads(response.content)
    returned_ids = {item["id"] for item in body["results"]}
    assert str(ids["alpha"]) in returned_ids
    assert str(ids["beta"]) not in returned_ids
    assert "beta" not in response.content.decode()  # no cross-tenant identifiers leak


@pytest.mark.django_db(databases=TENANT_DBS)
def test_token_for_tenant_a_is_rejected_on_tenant_b(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    _seed_events(tenants)
    alpha_token = token_factory.mint("alpha")  # issued by alpha's realm
    response = Client().get(
        "/api/v1/audit/events",
        headers={"X-Tenant-ID": "beta", "Authorization": f"Bearer {alpha_token}"},
    )
    # Issuer binding: beta's expected issuer != alpha token issuer -> authentication fails.
    assert response.status_code == 401
    assert b"seed" not in response.content


@pytest.mark.django_db(databases=TENANT_DBS)
def test_missing_token_is_401_and_role_without_permission_is_403(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    no_token = Client().get("/api/v1/audit/events", headers={"X-Tenant-ID": "alpha"})
    assert no_token.status_code == 401

    unprivileged = token_factory.mint("alpha", roles=("teller",))
    response = Client().get(
        "/api/v1/audit/events",
        headers={"X-Tenant-ID": "alpha", "Authorization": f"Bearer {unprivileged}"},
    )
    assert response.status_code == 403


@pytest.mark.django_db(databases=TENANT_DBS)
def test_writes_land_only_in_the_owning_tenant_database(
    tenants: dict[str, Tenant],
) -> None:
    _seed_events(tenants)
    # Unscoped, per-database verification (bypasses the tenant manager on purpose).
    alpha_ops = set(
        AuditEvent._base_manager.using("tenant_alpha").values_list("operation", flat=True)
    )
    beta_ops = set(
        AuditEvent._base_manager.using("tenant_beta").values_list("operation", flat=True)
    )
    assert "seed.alpha" in alpha_ops and "seed.beta" not in alpha_ops
    assert "seed.beta" in beta_ops and "seed.alpha" not in beta_ops
