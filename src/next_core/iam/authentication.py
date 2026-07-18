"""OIDC bearer-token validation (ADR-0008).

Authentication is fully delegated to the external IAM. This boundary validates: signature
(via the issuer's JWKS), issuer, audience, and lifetime. The expected issuer is derived
from the *resolved tenant context* (realm-per-tenant), so a valid token from another
tenant's realm fails with 401 — tenant/token binding is structural, not a claim check.

Air-gap/test note: OIDC_JWKS_STATIC (a JWKS document in settings) bypasses network fetch;
otherwise JWKS is fetched from the issuer and cached per process.
"""

import threading
from typing import Any

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions
from rest_framework.request import Request

from next_core.iam.principal import AuthenticatedPrincipal
from next_core.platform.logging import logger
from next_core.tenancy.context import current_tenant

_jwks_clients: dict[str, jwt.PyJWKClient] = {}
_jwks_lock = threading.Lock()


def _expected_issuer(tenant_slug: str) -> str:
    template = getattr(settings, "OIDC_ISSUER_TEMPLATE", "")
    if not template:
        raise exceptions.AuthenticationFailed("IAM is not configured (OIDC_ISSUER_TEMPLATE).")
    return template.format(tenant=tenant_slug)


def _signing_key(token: str, issuer: str) -> jwt.PyJWK:
    static_jwks: dict[str, Any] | None = getattr(settings, "OIDC_JWKS_STATIC", None)
    if static_jwks is not None:
        header = jwt.get_unverified_header(token)
        for key in jwt.PyJWKSet.from_dict(static_jwks).keys:
            if key.key_id == header.get("kid"):
                return key
        raise exceptions.AuthenticationFailed("Unknown signing key.")
    # Live JWKS fetch from the IAM — a network call by nature; exercised against a real
    # Keycloak in the compose stack, not in the unit/integration suites (which pin
    # OIDC_JWKS_STATIC to avoid mocking our own validation logic).
    url_template = getattr(  # pragma: no cover
        settings, "OIDC_JWKS_URL_TEMPLATE", "{issuer}/protocol/openid-connect/certs"
    )
    url = url_template.format(issuer=issuer)  # pragma: no cover
    with _jwks_lock:  # pragma: no cover
        client = _jwks_clients.get(url)
        if client is None:
            client = jwt.PyJWKClient(url, cache_keys=True, lifespan=300)
            _jwks_clients[url] = client
    try:  # pragma: no cover
        return client.get_signing_key_from_jwt(token)
    except jwt.PyJWTError as exc:
        raise exceptions.AuthenticationFailed("Unable to resolve signing key.") from exc


def _roles_from_claims(claims: dict[str, Any]) -> frozenset[str]:
    path = getattr(settings, "OIDC_ROLES_CLAIM", "realm_access.roles")
    node: Any = claims
    for part in path.split("."):
        if not isinstance(node, dict):
            return frozenset()
        node = node.get(part)
    if isinstance(node, list):
        return frozenset(str(r) for r in node)
    return frozenset()


class OIDCAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[AuthenticatedPrincipal, str] | None:
        header = authentication.get_authorization_header(request).decode("ascii", "ignore")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Malformed Authorization header.")
        token = parts[1]

        tenant = current_tenant()  # middleware established it; raises otherwise
        issuer = _expected_issuer(tenant.slug)
        key = _signing_key(token, issuer)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=getattr(settings, "OIDC_AUDIENCE", "next-core"),
                issuer=issuer,
                leeway=30,
                options={"require": ["exp", "iss", "sub", "aud"]},
            )
        except jwt.PyJWTError as exc:
            logger.warning("iam.token.rejected", reason=type(exc).__name__)
            raise exceptions.AuthenticationFailed("Invalid token.") from exc

        principal = AuthenticatedPrincipal(
            subject=str(claims["sub"]),
            tenant_slug=tenant.slug,
            roles=_roles_from_claims(claims),
            is_service=bool(claims.get("client_id")) and "email" not in claims,
        )
        return principal, token

    def authenticate_header(self, request: Request) -> str:
        return f'{self.keyword} realm="next-core"'
