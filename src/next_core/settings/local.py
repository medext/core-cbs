"""Local development profile — the only profile where DEBUG and default secrets are legal."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "insecure-local-dev-key-do-not-deploy")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("DATABASE_URL", "postgres://nextcore@127.0.0.1:5433/next_core_dev")

from next_core.settings.base import *  # noqa: F403
from next_core.settings.base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# Local runs over plain HTTP.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

INSTALLED_APPS = [*INSTALLED_APPS, "next_core.control_plane"]  # noqa: F405
