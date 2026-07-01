"""Plumbing: the API boots and its read-only endpoints respond.

Skipped automatically if the optional 'api' extras aren't installed.
"""

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient

        from src.api import app
    except Exception as e:  # e.g. incompatible starlette in a dirty env
        pytest.skip(f"API dependencies unavailable: {e}")
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["version"]  # version is surfaced to the dashboard


def test_info_lists_tools(client):
    r = client.get("/info")
    assert r.status_code == 200
    assert "example_tool" in r.json()["tools"]
