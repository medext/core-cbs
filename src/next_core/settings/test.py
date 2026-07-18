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
