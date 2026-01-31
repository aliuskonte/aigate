"""Tests for /metrics endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from aigate.main import create_app


def test_metrics_returns_prometheus_format() -> None:
    """Metrics endpoint returns Prometheus text format."""
    from aigate.core.auth import AuthContext, get_auth_context
    from aigate.core.deps import get_provider_registry

    from aigate.providers.registry import ProviderRegistry

    app = create_app()
    registry = ProviderRegistry()

    def _auth_override():
        return AuthContext(org_id="org-1", api_key="agk_test")

    def _registry_override(_=None):
        return registry

    app.dependency_overrides[get_auth_context] = _auth_override
    app.dependency_overrides[get_provider_registry] = _registry_override

    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    assert "aigate_requests_total" in r.text or "aigate_request_duration_seconds" in r.text
