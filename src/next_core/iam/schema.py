"""OpenAPI description of the OIDC bearer authentication (drf-spectacular extension)."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class OIDCAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = "next_core.iam.authentication.OIDCAuthentication"
    name = "oidc"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Access token from the tenant's OIDC realm (ADR-0008).",
        }
