"""FR-12 API tests: the public health endpoint."""

from __future__ import annotations


def test_health_returns_ok_without_authentication(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok"}


def test_health_is_public_even_with_an_invalid_api_key(client):
    response = client.get("/health", headers={"X-API-Key": "not-a-real-key"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
