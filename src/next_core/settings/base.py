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
    "next_core.platform.outbox",
    "next_core.ledger",
    "next_core.parties",
    "next_core.products",
    "next_core.accounts",
    "next_core.transactions",
    "next_core.limits",
    "drf_spectacular",
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
NEXT_CORE_DATA_PLANE_APPS = (
    "audit",
    "outbox",
    "ledger",
    "parties",
    "products",
    "accounts",
    "transactions",
    "limits",
)
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
# Bounded lock waits (concurrency review C2): a blocked financial write fails fast as a
# retryable 503 instead of queueing forever behind a hot row.
DB_LOCK_TIMEOUT_MS = env.int("DATABASE_LOCK_TIMEOUT_MS", default=5000)
DATABASES["default"].setdefault("OPTIONS", {})["options"] = f"-c lock_timeout={DB_LOCK_TIMEOUT_MS}"

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
    # One RFC 9457 problem-details shape for every error (docs/api/error-catalog.md).
    "EXCEPTION_HANDLER": "next_core.platform.errors.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
}

# OpenAPI 3.1 contract (OD-6): generated from the code, committed as docs/api/openapi.json and
# contract-tested for drift.
SPECTACULAR_SETTINGS = {
    "TITLE": "Next Core API",
    "DESCRIPTION": (
        "Core banking API v1. Every data-plane call carries a tenant (X-Tenant-ID header in "
        "SaaS-dev/staging) and an OAuth2 bearer token. Financial writes require an "
        "Idempotency-Key header. Amounts are decimal strings in major units with the "
        "currency exponent (ADR-0004). Errors are RFC 9457 problem details."
    ),
    "VERSION": "1.0.0",
    "OAS_VERSION": "3.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "APPEND_COMPONENTS": {
        "securitySchemes": {"oidc": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}
    },
    "ENUM_NAME_OVERRIDES": {
        "PartyStatusEnum": "next_core.parties.models.PartyStatus",
        "PartyTypeEnum": "next_core.parties.models.PartyType",
        "KycStatusEnum": "next_core.parties.models.KycStatus",
        "AccountStatusEnum": "next_core.accounts.models.AccountStatus",
        "VersionStatusEnum": "next_core.products.models.VersionStatus",
        "TxnStateEnum": "next_core.transactions.models.TxnState",
        "TxnTypeEnum": "next_core.transactions.models.TxnType",
    },
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
