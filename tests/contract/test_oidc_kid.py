"""JWKS key-resolution contract: unknown kid is rejected."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import Client

from next_core.control_plane.models import Tenant
from tests.conftest import TENANT_DBS, TokenFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db(databases=TENANT_DBS)
def test_unknown_kid_is_rejected(tenants: dict[str, Tenant], token_factory: TokenFactory) -> None:
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "https://iam.test/realms/alpha",
            "aud": "next-core",
            "sub": "u1",
            "exp": now + 300,
            "iat": now,
        },
        rogue_key,
        algorithm="RS256",
        headers={"kid": "unknown-kid"},
    )
    response = Client().get(
        "/api/v1/audit/events",
        headers={"X-Tenant-ID": "alpha", "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
