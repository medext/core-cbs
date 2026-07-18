"""Tenant context: explicit, mandatory, non-nestable across tenants."""

import uuid

import pytest

from next_core.tenancy.context import TenantContext, current_tenant, tenant_context
from next_core.tenancy.exceptions import TenantContextMissingError

ALPHA = TenantContext(tenant_id=uuid.uuid4(), slug="alpha", db_alias="tenant_alpha")
BETA = TenantContext(tenant_id=uuid.uuid4(), slug="beta", db_alias="tenant_beta")


def test_current_tenant_raises_without_context() -> None:
    with pytest.raises(TenantContextMissingError):
        current_tenant()


def test_context_is_established_and_cleared() -> None:
    with tenant_context(ALPHA) as ctx:
        assert current_tenant() is ctx
    with pytest.raises(TenantContextMissingError):
        current_tenant()


def test_nesting_a_different_tenant_is_refused() -> None:
    with tenant_context(ALPHA), pytest.raises(TenantContextMissingError), tenant_context(BETA):
        pass  # pragma: no cover


def test_renesting_same_tenant_is_allowed() -> None:
    with tenant_context(ALPHA), tenant_context(ALPHA):
        assert current_tenant().slug == "alpha"


def test_context_cleared_even_on_exception() -> None:
    with pytest.raises(RuntimeError), tenant_context(ALPHA):
        raise RuntimeError("boom")
    with pytest.raises(TenantContextMissingError):
        current_tenant()
