"""Cross-cutting API tests: consistent envelopes for 404/405/422/500."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.support import AUTH, DESTINATION, assert_error


def test_unmatched_public_path_returns_json_404(client):
    response = client.get("/one/two")

    assert_error(response, 404, "not_found")


def test_method_not_allowed_returns_json_405(client):
    response = client.post("/health")

    assert_error(response, 405, "method_not_allowed")


def test_method_not_allowed_on_api_route_returns_json_405(client):
    response = client.get("/api/links", headers=AUTH)

    assert_error(response, 405, "method_not_allowed")


def test_malformed_json_body_returns_json_422(client):
    response = client.post(
        "/api/links",
        content=b"{this is not json",
        headers={**AUTH, "Content-Type": "application/json"},
    )

    error = assert_error(response, 422, "validation_error")
    assert "Traceback" not in error["message"]


def test_unexpected_exception_returns_json_500_without_internals(app, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("super secret internal detail")

    monkeypatch.setattr(app.state.repository, "create", explode)

    with TestClient(
        app, raise_server_exceptions=False, follow_redirects=False
    ) as client:
        response = client.post(
            "/api/links", json={"url": DESTINATION}, headers=AUTH
        )

    error = assert_error(response, 500, "internal_error")
    assert "super secret internal detail" not in response.text
    assert "super secret internal detail" not in error["message"]
