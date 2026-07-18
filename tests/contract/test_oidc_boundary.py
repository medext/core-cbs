"""OIDC boundary contract: what the IAM must present, and everything we reject.

The IAM is a true external boundary — tokens are minted with a local RSA key and validated
against a static JWKS (no mocked internals of our own code).
"""

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import Client

from next_core.control_plane.models import Tenant
from tests.conftest import TENANT_DBS, TokenFactory

pytestmark = pytest.mark.integration

URL = "/api/v1/audit/events"


def _call(token: str) -> int:
    return (
        Client()
        .get(URL, headers={"X-Tenant-ID": "alpha", "Authorization": f"Bearer {token}"})
        .status_code
    )


@pytest.mark.django_db(databases=TENANT_DBS)
def test_valid_token_is_accepted(tenants: dict[str, Tenant], token_factory: TokenFactory) -> None:
    assert _call(token_factory.mint("alpha")) == 200


@pytest.mark.django_db(databases=TENANT_DBS)
def test_expired_token_is_rejected(tenants: dict[str, Tenant], token_factory: TokenFactory) -> None:
    assert _call(token_factory.mint("alpha", expires_in=-3600)) == 401


@pytest.mark.django_db(databases=TENANT_DBS)
def test_wrong_audience_is_rejected(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    assert _call(token_factory.mint("alpha", audience="another-api")) == 401


@pytest.mark.django_db(databases=TENANT_DBS)
def test_wrong_issuer_is_rejected(tenants: dict[str, Tenant], token_factory: TokenFactory) -> None:
    assert _call(token_factory.mint("alpha", issuer="https://evil.example/realms/alpha")) == 401


@pytest.mark.django_db(databases=TENANT_DBS)
def test_foreign_signature_is_rejected(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert _call(token_factory.mint("alpha", key=foreign_key)) == 401


@pytest.mark.django_db(databases=TENANT_DBS)
def test_missing_required_claims_are_rejected(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    assert _call(token_factory.mint("alpha", drop_claims=("exp",))) == 401
    assert _call(token_factory.mint("alpha", drop_claims=("sub",))) == 401


@pytest.mark.django_db(databases=TENANT_DBS)
def test_malformed_authorization_headers_are_rejected(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    client = Client()
    for header in ("Bearer", "Basic dXNlcjpwYXNz", "Bearer a b c"):
        response = client.get(URL, headers={"X-Tenant-ID": "alpha", "Authorization": header})
        assert response.status_code == 401, header
