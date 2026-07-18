"""Settings-profile guarantees: secure-by-default, no secrets baked into saas/onprem."""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration


def _import_profile(profile: str, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": "src",
        "DJANGO_SETTINGS_MODULE": f"next_core.settings.{profile}",
        **extra_env,
    }
    code = "import django; django.setup(); from django.conf import settings; print(settings.DEBUG)"
    return subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60
    )


def test_saas_profile_refuses_to_boot_without_secret_key() -> None:
    result = _import_profile(
        "saas",
        {
            "DJANGO_ALLOWED_HOSTS": "api.example.com",
            "DATABASE_URL": "postgres://u@h/db",
        },
    )
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_saas_profile_boots_with_env_and_forces_debug_off() -> None:
    result = _import_profile(
        "saas",
        {
            "DJANGO_SECRET_KEY": "test-only-key",
            "DJANGO_ALLOWED_HOSTS": "api.example.com",
            "DATABASE_URL": "postgres://u@h/db",
            "DJANGO_DEBUG": "true",  # must be ignored: saas never enables DEBUG
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_onprem_profile_forces_debug_off() -> None:
    result = _import_profile(
        "onprem",
        {
            "DJANGO_SECRET_KEY": "test-only-key",
            "DJANGO_ALLOWED_HOSTS": "bank.internal",
            "DATABASE_URL": "postgres://u@h/db",
            "DJANGO_DEBUG": "true",
            "NEXT_CORE_TENANT_ID": "7e6a6a1e-96b8-4dc0-a1a2-3c1f6f6b0001",
            "NEXT_CORE_TENANT_SLUG": "mainbank",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
