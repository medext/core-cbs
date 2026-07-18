"""Migration fan-out command: per-tenant, deterministic, refuses silent no-ops."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from next_core.control_plane.models import Tenant, TenantStatus
from tests.conftest import TENANT_DBS

pytestmark = pytest.mark.integration


@pytest.mark.django_db(databases=TENANT_DBS)
def test_fanout_migrates_every_active_tenant(tenants: dict[str, Tenant]) -> None:
    out = StringIO()
    call_command("migrate_tenants", stdout=out)
    text = out.getvalue()
    assert "[alpha -> tenant_alpha] OK" in text
    assert "[beta -> tenant_beta] OK" in text
    # Idempotent re-run (resume-after-partial-failure safety)
    out2 = StringIO()
    call_command("migrate_tenants", stdout=out2)
    assert "[beta -> tenant_beta] OK" in out2.getvalue()


@pytest.mark.django_db(databases=TENANT_DBS)
def test_single_tenant_flag_targets_only_that_tenant(tenants: dict[str, Tenant]) -> None:
    out = StringIO()
    call_command("migrate_tenants", tenant="alpha", stdout=out)
    text = out.getvalue()
    assert "[alpha -> tenant_alpha] OK" in text
    assert "beta" not in text


@pytest.mark.django_db(databases=TENANT_DBS)
def test_suspended_tenants_are_excluded(tenants: dict[str, Tenant]) -> None:
    Tenant.objects.filter(slug="beta").update(status=TenantStatus.SUSPENDED)
    out = StringIO()
    call_command("migrate_tenants", stdout=out)
    assert "beta" not in out.getvalue()


@pytest.mark.django_db(databases=TENANT_DBS)
def test_empty_registry_is_a_hard_error(db: None) -> None:
    with pytest.raises(CommandError, match="No active tenants"):
        call_command("migrate_tenants")


@pytest.mark.django_db(databases=TENANT_DBS)
def test_check_mode_passes_on_fully_migrated_tenants(tenants: dict[str, Tenant]) -> None:
    call_command("migrate_tenants", check=True, stdout=StringIO())
