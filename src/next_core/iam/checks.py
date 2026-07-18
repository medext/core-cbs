"""Django system checks guarding IAM/tenancy configuration invariants.

The issuer template is the structural binding between tokens and tenants (realm-per-tenant).
In any multi-tenant deployment a template without the ``{tenant}`` placeholder would give
every tenant the same issuer — one configuration mistake away from cross-tenant access —
so it fails startup, not review.
"""

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, register


@register("security")
def issuer_template_binds_tenant(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    directory = getattr(settings, "NEXT_CORE_TENANT_DIRECTORY", "control")
    template = getattr(settings, "OIDC_ISSUER_TEMPLATE", "")
    if directory != "static" and template and "{tenant}" not in template:
        return [
            Error(
                "OIDC_ISSUER_TEMPLATE must contain the '{tenant}' placeholder in "
                "multi-tenant deployments: a shared issuer would break tenant/token "
                "binding and allow cross-tenant access via the tenant header.",
                id="next_core.E001",
                obj="settings.OIDC_ISSUER_TEMPLATE",
            )
        ]
    return []
