"""Tenant resolution at the request boundary.

Resolution failure is a hard 400 — there is no default tenant (prohibited pattern).
Resolver strategies:
- ``header`` — tenant slug from the X-Tenant-ID header. Suitable for local/dev/test and
  staging behind a trusted gateway ONLY; production SaaS resolution (host- or token-based)
  is wired when public routing lands. The IAM layer additionally enforces that the
  authenticated principal belongs to the resolved tenant.
- ``static`` — the on-premise single tenant from configuration; the header is ignored.
"""

import re
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from next_core.platform.logging import logger
from next_core.tenancy.context import TenantContext, tenant_context
from next_core.tenancy.directory import get_directory
from next_core.tenancy.exceptions import TenantResolutionError

TENANT_HEADER = "X-Tenant-ID"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")

# Paths served without tenant scope (process-level infrastructure only).
_EXEMPT_PREFIXES = ("/health/",)


def _resolve(request: HttpRequest) -> TenantContext:
    strategy = getattr(settings, "NEXT_CORE_TENANT_RESOLVER", "header")
    directory = get_directory()
    if strategy == "static":
        return directory.all_active()[0]
    if strategy == "header":
        raw = request.headers.get(TENANT_HEADER, "").strip()
        if not raw:
            raise TenantResolutionError(f"Missing {TENANT_HEADER} header.")
        if not _SLUG_RE.match(raw):
            raise TenantResolutionError("Invalid tenant identifier.")
        return directory.lookup(raw)
    raise TenantResolutionError(f"Unknown tenant resolver strategy '{strategy}'.")


class TenantContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith(_EXEMPT_PREFIXES):
            return self.get_response(request)
        try:
            ctx = _resolve(request)
        except TenantResolutionError as exc:
            # Specific reason goes to server logs only; the response is deliberately
            # generic so unauthenticated callers cannot enumerate tenants or their
            # lifecycle status (existence oracle).
            logger.warning("tenancy.resolution_failed", reason=str(exc))
            return JsonResponse(
                {
                    "code": "TENANT_RESOLUTION_FAILED",
                    "title": "Tenant resolution failed",
                    "detail": "The request could not be attributed to a valid tenant.",
                    "correlation_id": getattr(request, "correlation_id", ""),
                    "retryable": False,
                },
                status=400,
            )
        with tenant_context(ctx):
            return self.get_response(request)
