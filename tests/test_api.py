"""Plumbing: the API boots and its read-only endpoints respond.

Skipped automatically if the optional 'api' extras aren't installed.
"""

import pytest


@pytest.fixture
def client(monkeypatch):
    pytest.importorskip("fastapi")
    # These are auth-agnostic plumbing checks; run them with auth off so /info is
    # reachable without a login. (Authed behavior is covered by test_auth_api.py.)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        from fastapi.testclient import TestClient

        from src.api import app
    except Exception as e:  # e.g. incompatible starlette in a dirty env
        pytest.skip(f"API dependencies unavailable: {e}")
    yield TestClient(app)
    get_settings.cache_clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["version"]  # version is surfaced to the dashboard
    assert body["name"]  # agent branding, drives the dashboard header pre-login


def test_info_lists_tools(client):
    r = client.get("/info")
    assert r.status_code == 200
    assert "example_tool" in r.json()["tools"]
