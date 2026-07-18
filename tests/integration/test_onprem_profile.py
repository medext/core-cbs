"""On-premise profile: boots and serves with the control-plane runtime absent (gate item)."""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration

_ONPREM_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "PYTHONPATH": "src",
    "DJANGO_SETTINGS_MODULE": "next_core.settings.onprem",
    "DJANGO_SECRET_KEY": "test-only-key",
    "DJANGO_ALLOWED_HOSTS": "bank.internal",
    "DATABASE_URL": "postgres://u@h/db",
    "NEXT_CORE_TENANT_ID": "7e6a6a1e-96b8-4dc0-a1a2-3c1f6f6b0001",
    "NEXT_CORE_TENANT_SLUG": "mainbank",
}


def _boot(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60
    )


def test_onprem_boots_without_control_plane_installed() -> None:
    code = (
        "import django; django.setup(); from django.conf import settings; "
        "apps = settings.INSTALLED_APPS; "
        "assert not any('control_plane' in a for a in apps), 'control plane present!'; "
        "assert settings.NEXT_CORE_TENANT_DIRECTORY == 'static'; "
        "assert 'tenant_main' in settings.DATABASES; "
        "from next_core.tenancy.directory import get_directory; "
        "ctx = get_directory().all_active()[0]; "
        "assert ctx.slug == 'mainbank' and ctx.db_alias == 'tenant_main'; "
        "print('onprem-ok')"
    )
    result = _boot(code, _ONPREM_ENV)
    assert result.returncode == 0, result.stderr
    assert "onprem-ok" in result.stdout


def test_onprem_refuses_to_boot_without_tenant_configuration() -> None:
    env = {k: v for k, v in _ONPREM_ENV.items() if not k.startswith("NEXT_CORE_TENANT")}
    result = _boot("import django; django.setup()", env)
    assert result.returncode != 0
    assert "NEXT_CORE_TENANT_ID" in result.stderr
