"""Base settings — shared by every profile.

Profiles (local/saas/onprem/test) import * from here and override only what their
deployment model requires. Secure-by-default: secrets and hosts come from the
environment; there are no production defaults.
"""

from pathlib import Path
from typing import Any

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

env = environ.Env()

SECRET_KEY: str = env("DJANGO_SECRET_KEY")  # no default: missing key must fail loudly
DEBUG: bool = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "next_core.platform.health",
    "next_core.tenancy",
    "next_core.iam",
    "next_core.audit",
    # control_plane is added by SaaS-family profiles only; absent on-premise (ADR-0005).
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "next_core.platform.logging.CorrelationIdMiddleware",
    "next_core.tenancy.middleware.TenantContextMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

DATABASE_ROUTERS = ["next_core.tenancy.router.TenantDatabaseRouter"]

# Tenancy (see docs/architecture/tenancy-and-deployment.md)
NEXT_CORE_DATA_PLANE_APPS = ("audit",)
NEXT_CORE_TENANT_RESOLVER = env("NEXT_CORE_TENANT_RESOLVER", default="header")
NEXT_CORE_TENANT_DIRECTORY = env("NEXT_CORE_TENANT_DIRECTORY", default="control")

# IAM boundary (ADR-0008): issuer is realm-per-tenant; audience fixed per deployment.
OIDC_ISSUER_TEMPLATE = env("OIDC_ISSUER_TEMPLATE", default="")
OIDC_AUDIENCE = env("OIDC_AUDIENCE", default="next-core")
OIDC_JWKS_URL_TEMPLATE = env(
    "OIDC_JWKS_URL_TEMPLATE", default="{issuer}/protocol/openid-connect/certs"
)

ROOT_URLCONF = "next_core.urls"
WSGI_APPLICATION = "next_core.wsgi.application"

TEMPLATES: list[dict[str, Any]] = []

# PostgreSQL is the sole authority for state (ADR-0003); no other engine is valid.
DATABASES = {"default": env.db_url("DATABASE_URL")}
if not DATABASES["default"]["ENGINE"].endswith("postgresql"):  # pragma: no cover - guard
    raise RuntimeError("DATABASE_URL must point to PostgreSQL (ADR-0003).")
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)

# Django's built-in Redis backend (not django-redis, which env.cache_url would select).
_redis_url = env("REDIS_URL", default="")
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _redis_url}
        if _redis_url
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Deny by default; endpoints opt in explicitly (health endpoints are plain Django views).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
    "DEFAULT_PAGINATION_CLASS": "next_core.platform.api.BoundedPageNumberPagination",
    "PAGE_SIZE": 50,
}

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Hardening defaults (profiles relax only where their transport model justifies it)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440  # 2.5 MiB request-size bound at the app layer

LOG_LEVEL: str = env("LOG_LEVEL", default="INFO")

from next_core.platform.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(LOG_LEVEL)
