"""Health readiness must fail closed when a dependency is down (fault injection).

Fault injection here patches the platform boundary (cursor/cache call sites) to simulate an
unreachable dependency; this is platform plumbing, not financial logic — the happy path is
proven against real PostgreSQL in test_health.py.
"""

import json
from typing import Any

import pytest
from django.db import OperationalError
from django.test import Client

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_ready_returns_503_when_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.db import connection

    def broken_cursor(*args: Any, **kwargs: Any) -> Any:
        raise OperationalError("simulated: database unreachable")

    monkeypatch.setattr(connection, "cursor", broken_cursor)
    response = Client().get("/health/ready")
    body = json.loads(response.content)
    assert response.status_code == 503
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == "error"


@pytest.mark.django_db
def test_ready_returns_503_when_cache_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.core import cache as cache_module

    def broken_set(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("simulated: cache unreachable")

    monkeypatch.setattr(cache_module.cache, "set", broken_set)
    response = Client().get("/health/ready")
    body = json.loads(response.content)
    assert response.status_code == 503
    assert body["checks"]["cache"] == "error"
    assert body["checks"]["database"] == "ok"  # DB stays healthy; only cache fails
