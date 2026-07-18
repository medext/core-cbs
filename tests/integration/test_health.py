"""Health endpoints against real PostgreSQL (integration — never SQLite)."""

import json

import pytest
from django.test import Client

from next_core.platform.logging import CORRELATION_HEADER

pytestmark = pytest.mark.integration


def test_live_returns_ok_without_touching_dependencies() -> None:
    response = Client().get("/health/live")
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}


@pytest.mark.django_db
def test_ready_returns_ok_with_real_database() -> None:
    response = Client().get("/health/ready")
    body = json.loads(response.content)
    assert response.status_code == 200, body
    assert body == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


def test_correlation_id_present_on_health_responses() -> None:
    response = Client().get("/health/live")
    assert response[CORRELATION_HEADER]
