"""Authenticated principal — the identity asserted by the external IAM (ADR-0008)."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Identity extracted from a validated OIDC token. Authorization decisions are made
    by Next Core's permission model, never by trusting fine-grained claims."""

    subject: str
    tenant_slug: str
    roles: frozenset[str] = field(default_factory=frozenset)
    is_service: bool = False

    # DRF integration surface
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_staff(self) -> bool:  # Django admin is never reachable with an API token
        return False

    def __str__(self) -> str:
        return f"{self.subject}@{self.tenant_slug}"
