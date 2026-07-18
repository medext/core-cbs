"""Test profile — real PostgreSQL (never SQLite), fast hashing, deterministic config."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "insecure-test-key")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
os.environ.setdefault(
    "DATABASE_URL",
    f"postgres://nextcore@127.0.0.1:{os.environ.get('TEST_DB_PORT', '5433')}/next_core_dev",
)

from next_core.settings.base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed; tests only

INSTALLED_APPS = [*INSTALLED_APPS, "next_core.control_plane"]  # noqa: F405

# Two static tenant databases on the same test server prove routing & isolation on real
# PostgreSQL. (Runtime alias registration from DSNs is unit-tested separately.)
for _alias, _db in (("tenant_alpha", "next_core_ta"), ("tenant_beta", "next_core_tb")):
    DATABASES[_alias] = {**DATABASES["default"], "NAME": _db}  # noqa: F405

OIDC_ISSUER_TEMPLATE = "https://iam.test/realms/{tenant}"
OIDC_AUDIENCE = "next-core"
