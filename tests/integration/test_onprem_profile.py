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


def test_onprem_migrates_bootstraps_and_verifies_on_real_postgres() -> None:
    """Regression (CI onprem-boot): with one physical database behind both aliases, the
    data-plane tables must actually be created, then bootstrap + integrity must succeed."""
    import psycopg

    port = os.environ.get("TEST_DB_PORT", "5433")
    base = os.environ.get("DATABASE_URL", f"postgres://nextcore@127.0.0.1:{port}/next_core_dev")
    dbname = "next_core_onprem_regression"
    with psycopg.connect(base, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [dbname]).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')
    env = {
        **_ONPREM_ENV,
        "DATABASE_URL": base.rsplit("/", 1)[0] + "/" + dbname,
        "DJANGO_SECURE_SSL_REDIRECT": "false",
    }
    for args in (
        ["migrate", "--noinput"],
        ["migrate_tenants"],
        ["bootstrap_tenant"],
        ["bootstrap_tenant"],
        ["verify_ledger"],
    ):
        result = subprocess.run(
            [sys.executable, "manage.py", *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, (args, result.stderr[-2000:])
    assert "-> OK" in result.stdout
