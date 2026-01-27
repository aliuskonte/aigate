from __future__ import annotations

from fastapi.testclient import TestClient

from aigate.main import create_app


def test_health_ok() -> None:
    app = create_app()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
