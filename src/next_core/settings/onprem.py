"""On-premise single-tenant profile — same hardening as SaaS; transport is customer-managed.

The control-plane runtime is absent in this profile (ADR-0005); nothing here may assume it.
TLS may terminate on a customer load balancer or on the app itself, so redirect/HSTS are
env-controlled with safe defaults.
"""

from next_core.settings.base import *  # noqa: F403
from next_core.settings.base import env

DEBUG = False  # never configurable in this profile

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
