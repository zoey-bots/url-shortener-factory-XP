"""FR-8 API tests: every ``/api/*`` path is authenticated, before parsing."""

from __future__ import annotations

import sqlite3

import pytest

from app.auth import hash_key
from tests.support import (
    API_KEY,
    AUTH,
    DESTINATION,
    SECOND_API_KEY,
    SECOND_AUTH,
    assert_error,
    create_link,
)

PROTECTED_CALLS = [
    ("POST", "/api/links"),
    ("GET", "/api/links/abc1234"),
    ("DELETE", "/api/links/abc1234"),
    ("GET", "/api/links/abc1234/stats"),
    ("GET", "/api/links"),
    ("GET", "/api/does-not-exist"),
    ("PUT", "/api/links"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_CALLS)
def test_missing_key_is_rejected_on_every_api_path(client, method, path):
    response = client.request(method, path)

    assert_error(response, 401, "unauthorized")
    assert API_KEY not in response.text


@pytest.mark.parametrize(("method", "path"), PROTECTED_CALLS)
def test_invalid_key_is_rejected_on_every_api_path(client, method, path):
    response = client.request(
        method, path, headers={"X-API-Key": "definitely-wrong"}
    )

    assert_error(response, 401, "unauthorized")


def test_valid_key_reaches_the_route(client):
    response = create_link(client)

    assert response.status_code == 201
    assert response.json()["url"] == DESTINATION


def test_unknown_api_path_with_valid_key_gets_json_404(client):
    response = client.get("/api/does-not-exist", headers=AUTH)

    assert_error(response, 404, "not_found")


def test_authentication_happens_before_body_validation(client):
    response = client.post("/api/links", json={"url": 123})

    assert_error(response, 401, "unauthorized")


def test_valid_key_still_reaches_body_validation(client):
    response = client.post("/api/links", json={"url": 123}, headers=AUTH)

    assert_error(response, 422, "validation_error")


def test_every_configured_key_is_accepted(client_factory):
    client = client_factory(api_keys=(API_KEY, SECOND_API_KEY))

    first = create_link(client, headers=AUTH)
    second = create_link(client, headers=SECOND_AUTH)

    assert first.status_code == 201
    assert second.status_code == 201


def test_empty_key_configuration_fails_closed(client_factory):
    client = client_factory(api_keys=())

    assert_error(create_link(client), 401, "unauthorized")
    assert_error(
        client.post(
            "/api/links",
            json={"url": DESTINATION},
            headers={"X-API-Key": API_KEY},
        ),
        401,
        "unauthorized",
    )
    assert_error(client.get("/api/anything"), 401, "unauthorized")
    assert client.get("/health").status_code == 200


def test_only_the_hashed_key_is_persisted(client_factory, tmp_path):
    client = client_factory()
    assert create_link(client).status_code == 201

    connection = sqlite3.connect(tmp_path / "links.db")
    try:
        rows = connection.execute(
            "SELECT DISTINCT key_hash FROM rate_limit_events"
        ).fetchall()
    finally:
        connection.close()

    stored = [row[0] for row in rows]
    assert stored == [hash_key(API_KEY)]
    assert API_KEY not in stored
    assert all(len(value) == 64 for value in stored)


def test_redirects_are_public(client):
    created = create_link(client).json()

    response = client.get(f"/{created['code']}")

    assert response.status_code == 302
    assert response.headers["location"] == DESTINATION
