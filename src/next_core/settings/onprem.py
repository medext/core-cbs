"""On-premise single-tenant profile — same hardening as SaaS; transport is customer-managed.

The control-plane runtime is absent in this profile (ADR-0005); nothing here may assume it.
TLS may terminate on a customer load balancer or on the app itself, so redirect/HSTS are
env-controlled with safe defaults.
"""

from next_core.settings.base import *  # noqa: F403
from next_core.settings.base import env

DEBUG = False  # never configurable in this profile

# Single static tenant; the control-plane runtime is absent (ADR-0005).
NEXT_CORE_TENANT_RESOLVER = "static"
NEXT_CORE_TENANT_DIRECTORY = "static"
NEXT_CORE_TENANT_ID = env("NEXT_CORE_TENANT_ID")  # required; no default
NEXT_CORE_TENANT_SLUG = env("NEXT_CORE_TENANT_SLUG")
NEXT_CORE_TENANT_DB_ALIAS = "tenant_main"

# One physical database serves both aliases: Django internals via 'default',
# data-plane models via 'tenant_main' (uniform router behavior across profiles).
DATABASES["tenant_main"] = dict(DATABASES["default"])  # noqa: F405

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
