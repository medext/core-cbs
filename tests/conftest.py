"""Shared test fixtures. Real PostgreSQL only — SQLite is never evidence (test rules).

JWT fixtures mint tokens with a locally-generated RSA key and expose the matching JWKS via
OIDC_JWKS_STATIC — mocking at the true external boundary (the IAM), never the database.
"""

import base64
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings

from next_core.control_plane.models import Tenant, TenantStatus

TENANT_DBS = ["default", "tenant_alpha", "tenant_beta"]


# --- Tenants ------------------------------------------------------------------------------


@pytest.fixture()
def tenants(db: None) -> dict[str, Tenant]:
    """Two ACTIVE tenants whose aliases are preconfigured in test settings."""
    result: dict[str, Tenant] = {}
    for slug in ("alpha", "beta"):
        result[slug] = Tenant.objects.create(
            id=uuid.uuid4(),
            slug=slug,
            name=slug.title(),
            status=TenantStatus.ACTIVE,
            db_alias=f"tenant_{slug}",
            database_dsn=f"postgres://test-preconfigured/{slug}",
        )
    return result


# --- OIDC tokens --------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = "test-key-1"


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwks() -> dict[str, Any]:
    numbers = _PRIVATE_KEY.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": _KID,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url_uint(numbers.n),
                "e": _b64url_uint(numbers.e),
            }
        ]
    }


@dataclass(frozen=True)
class TokenFactory:
    issuer_template: str = "https://iam.test/realms/{tenant}"
    audience: str = "next-core"

    def mint(
        self,
        tenant_slug: str,
        *,
        subject: str = "user-1",
        roles: tuple[str, ...] = ("auditor",),
        expires_in: int = 300,
        audience: str | None = None,
        issuer: str | None = None,
        drop_claims: tuple[str, ...] = (),
        key: rsa.RSAPrivateKey | None = None,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": issuer or self.issuer_template.format(tenant=tenant_slug),
            "aud": audience or self.audience,
            "sub": subject,
            "exp": now + expires_in,
            "iat": now,
            "realm_access": {"roles": list(roles)},
        }
        for name in drop_claims:
            claims.pop(name, None)
        return jwt.encode(claims, key or _PRIVATE_KEY, algorithm="RS256", headers={"kid": _KID})


@pytest.fixture()
def token_factory() -> Iterator[TokenFactory]:
    with override_settings(OIDC_JWKS_STATIC=_jwks()):
        yield TokenFactory()
