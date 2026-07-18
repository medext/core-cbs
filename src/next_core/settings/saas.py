"""SaaS profile (shared or dedicated) — TLS-terminated at the ingress, strict transport."""

from next_core.settings.base import *  # noqa: F403

DEBUG = False  # never configurable in this profile

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
