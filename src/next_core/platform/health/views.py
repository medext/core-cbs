"""Health endpoints.

- /health/live  — process is up; no dependency checks (for liveness probes).
- /health/ready — fails closed if PostgreSQL or the cache is unreachable (readiness probes).

Plain Django views: health must not depend on auth, DRF, or any domain machinery, and must
never leak internals (errors are reported as component status only).
"""

from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse

from next_core.platform.logging import logger


def live(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def ready(request: HttpRequest) -> JsonResponse:
    checks: dict[str, str] = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception:
        logger.warning("health.ready.database_unreachable")
        checks["database"] = "error"

    try:
        cache.set("health:ready", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("health:ready") == "1" else "error"
    except Exception:
        logger.warning("health.ready.cache_unreachable")
        checks["cache"] = "error"

    healthy = all(state == "ok" for state in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
    )
