"""Tenant directory and runtime alias registration guards."""

import pytest
from django.db import connections
from django.test import override_settings

from next_core.tenancy.directory import StaticDirectory, register_tenant_alias
from next_core.tenancy.exceptions import TenantResolutionError


def test_register_refuses_non_tenant_alias() -> None:
    with pytest.raises(TenantResolutionError):
        register_tenant_alias("default", "postgres://u@h/db")


def test_register_refuses_non_postgres_dsn() -> None:
    with pytest.raises(TenantResolutionError):
        register_tenant_alias("tenant_evil", "sqlite:///tmp/x.db")
    assert "tenant_evil" not in connections.databases


def test_register_is_idempotent_for_known_alias() -> None:
    # tenant_alpha is preconfigured in test settings; registering again must not clobber it.
    before = connections.databases["tenant_alpha"]
    register_tenant_alias("tenant_alpha", "postgres://other@elsewhere/db")
    assert connections.databases["tenant_alpha"] is before


def test_static_directory_requires_complete_configuration() -> None:
    with override_settings(), pytest.raises(TenantResolutionError):
        StaticDirectory().all_active()


@override_settings(
    NEXT_CORE_TENANT_ID="7e6a6a1e-96b8-4dc0-a1a2-3c1f6f6b0001",
    NEXT_CORE_TENANT_SLUG="mainbank",
    NEXT_CORE_TENANT_DB_ALIAS="tenant_main",
)
def test_static_directory_returns_configured_tenant_and_rejects_others() -> None:
    directory = StaticDirectory()
    ctx = directory.lookup("mainbank")
    assert ctx.db_alias == "tenant_main"
    assert [c.slug for c in directory.all_active()] == ["mainbank"]
    with pytest.raises(TenantResolutionError):
        directory.lookup("othertenant")
