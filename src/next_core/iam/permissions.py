"""Permission registry and enforcement.

Permissions are Next Core concepts; the IAM asserts identity and coarse roles only
(ADR-0008). Every endpoint names its permission explicitly — "authenticated" is never
sufficient. Role bundles below are seeds; institutions recompose them via configuration
in later phases (maker-checker arrives with the configuration workflow, Phase 6).
"""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from next_core.iam.principal import AuthenticatedPrincipal

# --- Registry (append-only; referenced by the authorization matrix doc) -------------------
AUDIT_READ = "audit:read"

PERMISSIONS: frozenset[str] = frozenset({AUDIT_READ})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "auditor": frozenset({AUDIT_READ}),
    "platform_ops": frozenset({AUDIT_READ}),
}


def permissions_for(roles: frozenset[str]) -> frozenset[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def require_permission(code: str) -> type[BasePermission]:
    """DRF permission class enforcing one registered permission code."""
    if code not in PERMISSIONS:
        raise ValueError(f"Unregistered permission code '{code}'.")

    class _RequirePermission(BasePermission):
        message = "Permission denied."
        required = code

        def has_permission(self, request: Request, view: APIView) -> bool:
            principal: Any = request.user
            if not isinstance(principal, AuthenticatedPrincipal):
                return False
            return code in permissions_for(principal.roles)

    return _RequirePermission
