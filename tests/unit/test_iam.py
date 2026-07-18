"""IAM unit coverage: principal surface, permission registry, config guards."""

import pytest
from rest_framework import exceptions

from next_core.iam.authentication import _expected_issuer, _roles_from_claims
from next_core.iam.permissions import (
    AUDIT_READ,
    permissions_for,
    require_permission,
)
from next_core.iam.principal import AuthenticatedPrincipal


def test_principal_drf_surface() -> None:
    principal = AuthenticatedPrincipal(subject="u1", tenant_slug="alpha")
    assert principal.is_authenticated is True
    assert principal.is_anonymous is False
    assert principal.is_staff is False
    assert str(principal) == "u1@alpha"


def test_permissions_expand_from_roles() -> None:
    assert AUDIT_READ in permissions_for(frozenset({"auditor"}))
    assert permissions_for(frozenset({"unknown-role"})) == frozenset()
    assert permissions_for(frozenset()) == frozenset()


def test_unregistered_permission_code_is_refused() -> None:
    with pytest.raises(ValueError, match="Unregistered"):
        require_permission("nonexistent:perm")


def test_missing_issuer_template_fails_authentication(settings: object) -> None:
    settings.OIDC_ISSUER_TEMPLATE = ""  # type: ignore[attr-defined]
    with pytest.raises(exceptions.AuthenticationFailed):
        _expected_issuer("alpha")


def test_roles_claim_extraction_tolerates_missing_paths() -> None:
    assert _roles_from_claims({"realm_access": {"roles": ["a", "b"]}}) == frozenset({"a", "b"})
    assert _roles_from_claims({}) == frozenset()
    assert _roles_from_claims({"realm_access": "notadict"}) == frozenset()
    assert _roles_from_claims({"realm_access": {"roles": "notalist"}}) == frozenset()
