"""FR-10 API tests: creation rate limiting, persistence and isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.support import (
    API_KEY,
    AUTH,
    SECOND_API_KEY,
    SECOND_AUTH,
    assert_error,
    create_link,
    make_settings,
)


def test_sixty_creations_are_allowed_then_the_sixty_first_is_429(client):
    for _ in range(60):
        assert create_link(client).status_code == 201

    response = create_link(client)

    assert_error(response, 429, "rate_limited")
    retry_after = response.headers.get("Retry-After")
    assert retry_after is not None
    assert retry_after.isdigit()
    assert 1 <= int(retry_after) <= 60
    assert API_KEY not in response.text


def test_budget_is_per_key_and_survives_an_application_restart(tmp_path):
    settings = make_settings(
        tmp_path / "shared.db", api_keys=(API_KEY, SECOND_API_KEY)
    )

    with TestClient(create_app(settings), follow_redirects=False) as first:
        for _ in range(60):
            assert create_link(first).status_code == 201
        assert_error(create_link(first), 429, "rate_limited")

        # A different configured key has its own independent budget.
        assert create_link(first, headers=SECOND_AUTH).status_code == 201

    # A brand-new application (a fresh "process") must reuse the SQLite
    # window instead of resetting it.
    with TestClient(create_app(settings), follow_redirects=False) as second:
        assert_error(create_link(second), 429, "rate_limited")
        assert create_link(second, headers=SECOND_AUTH).status_code == 201


def test_only_creation_consumes_quota(client):
    created = create_link(client).json()
    code = created["code"]
    for _ in range(58):
        assert create_link(client).status_code == 201

    # Public and read-only traffic must not consume the creation budget.
    for _ in range(5):
        assert client.get(f"/api/links/{code}", headers=AUTH).status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get(f"/{code}").status_code == 302

    # This is request 60 and must still be accepted.
    assert create_link(client).status_code == 201
    assert_error(create_link(client), 429, "rate_limited")

    # Everything else keeps working after the limit is hit.
    assert client.get("/health").status_code == 200
    assert client.get(f"/{code}").status_code == 302
    assert client.get(f"/api/links/{code}", headers=AUTH).status_code == 200
    assert client.get(f"/api/links/{code}/stats", headers=AUTH).status_code == 200


def test_rejected_authentication_does_not_consume_the_valid_key_budget(client):
    for _ in range(61):
        response = create_link(client, headers={"X-API-Key": "wrong-key"})
        assert_error(response, 401, "unauthorized")

    for _ in range(60):
        assert create_link(client).status_code == 201

    assert_error(create_link(client), 429, "rate_limited")
