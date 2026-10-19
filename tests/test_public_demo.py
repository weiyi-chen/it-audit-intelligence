from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.rate_limit import enforce_demo_rate_limit, reset_rate_limits


def _request(ip: str = "203.0.113.10") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/pbc/generate",
            "headers": [],
            "client": (ip, 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_application_imports_and_exposes_health_route(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "true")
    from api.main import app
    from api.checkpointer import get_checkpointer
    from langgraph.checkpoint.base import BaseCheckpointSaver

    assert any(route.path == "/health" for route in app.routes)
    assert isinstance(get_checkpointer(), BaseCheckpointSaver)
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["public_demo"] is True


def test_public_demo_hides_shared_history(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "true")
    from api.main import app

    client = TestClient(app)
    response = client.get("/api/pbc/history")
    assert response.status_code == 200
    assert response.json() == {"runs": [], "total": 0}

    response = client.get("/api/pbc/runs/1")
    assert response.status_code == 403


def test_public_demo_rate_limit(monkeypatch):
    monkeypatch.setenv("DEMO_RATE_LIMIT_PER_HOUR", "2")
    reset_rate_limits()

    enforce_demo_rate_limit(_request())
    enforce_demo_rate_limit(_request())

    try:
        enforce_demo_rate_limit(_request())
    except HTTPException as exc:
        assert exc.status_code == 429
        assert exc.headers and "Retry-After" in exc.headers
    else:
        raise AssertionError("Expected the third request to be rate limited")


def test_forwarded_clients_have_separate_allowances(monkeypatch):
    monkeypatch.setenv("DEMO_RATE_LIMIT_PER_HOUR", "1")
    reset_rate_limits()

    first = _request()
    first.scope["headers"] = [(b"x-forwarded-for", b"198.51.100.1, 10.0.0.1")]
    second = _request()
    second.scope["headers"] = [(b"x-forwarded-for", b"198.51.100.2, 10.0.0.1")]

    enforce_demo_rate_limit(first)
    enforce_demo_rate_limit(second)
