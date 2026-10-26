"""FR-1/3/4/5/11 API tests: creation, codes, validation and aliases."""

from __future__ import annotations

from datetime import datetime, timedelta
import re

import pytest

from tests.support import (
    AUTH,
    BASE_URL,
    DESTINATION,
    assert_error,
    create_link,
)

CODE_PATTERN = re.compile(r"[A-Za-z0-9]{7}\Z")
EXTERNAL = "https://example.com/another"


# ---------------------------------------------------------------------------
# FR-1: create a short link
# ---------------------------------------------------------------------------


def test_create_returns_201_and_the_documented_contract(client):
    response = create_link(client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"code", "short_url", "url", "created_at", "expires_at"}
    assert CODE_PATTERN.fullmatch(body["code"])
    assert body["url"] == DESTINATION
    assert body["short_url"] == f"{BASE_URL}/{body['code']}"
    assert body["expires_at"] is None


def test_created_at_is_timezone_aware_utc(client):
    body = create_link(client).json()

    created_at = datetime.fromisoformat(body["created_at"])
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() == timedelta(0)


def test_supplied_expiry_is_normalised_to_utc(client):
    response = create_link(
        client, expires_at="2030-06-01T10:00:00+02:00"
    )

    assert response.status_code == 201
    assert response.json()["expires_at"] == "2030-06-01T08:00:00+00:00"


def test_past_expiry_is_accepted_at_creation(client):
    response = create_link(client, expires_at="2000-01-01T00:00:00Z")

    assert response.status_code == 201
    assert response.json()["expires_at"] == "2000-01-01T00:00:00+00:00"


def test_created_link_is_readable_through_the_api(client):
    created = create_link(client).json()

    response = client.get(f"/api/links/{created['code']}", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == created


# ---------------------------------------------------------------------------
# FR-3: code generation
# ---------------------------------------------------------------------------


def test_auto_generated_codes_are_seven_base62_characters(client):
    for _ in range(5):
        body = create_link(client).json()
        assert len(body["code"]) == 7
        assert CODE_PATTERN.fullmatch(body["code"])
        assert body["code"].isalnum()


def test_auto_generated_codes_are_unique(client):
    codes = set()

    for _ in range(15):
        response = create_link(client)
        assert response.status_code == 201
        codes.add(response.json()["code"])

    assert len(codes) == 15


# ---------------------------------------------------------------------------
# FR-4: URL validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com/file",
        "not-a-url",
        "//example.com/path",
        "https://",
        "https://user:secret@example.com/path",
        "https://exa mple.com/path",
        "https://example.com/\x00",
        "https://example.com:0/path",
        "https://example.com:65536/path",
        "https://example.com:/path",
        "https://example.com:not-a-port/path",
    ],
)
def test_invalid_urls_return_422_with_a_clear_message(client, url):
    response = create_link(client, url=url)

    error = assert_error(response, 422, "validation_error")
    assert "url" in error["message"].lower()


def test_url_longer_than_2048_characters_is_rejected(client):
    url = "https://example.com/" + "a" * (2049 - len("https://example.com/"))

    response = create_link(client, url=url)

    error = assert_error(response, 422, "validation_error")
    assert "2048" in error["message"]


def test_url_of_exactly_2048_characters_is_accepted(client):
    url = "https://example.com/" + "a" * (2048 - len("https://example.com/"))

    response = create_link(client, url=url)

    assert response.status_code == 201
    assert response.json()["url"] == url


@pytest.mark.parametrize("url", [123, 12.5, True, None, {"a": 1}, ["x"]])
def test_non_string_urls_are_rejected_without_coercion(client, url):
    response = create_link(client, url=url)

    assert_error(response, 422, "validation_error")


def test_credentials_are_not_echoed_in_the_error(client):
    response = create_link(
        client, url="https://user:super-secret@example.com/path"
    )

    assert_error(response, 422, "validation_error")
    assert "super-secret" not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/back",
        "http://LOCALHOST.:8000/back",
        "https://localhost:9999/back",
        "http://localhost/back",
    ],
)
def test_links_back_to_the_service_are_rejected(client, url):
    response = create_link(client, url=url)

    error = assert_error(response, 422, "validation_error")
    assert "back to this service" in error["message"]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/?next=http://localhost:8000/abc",
        "https://localhost.example.com/abc",
        "https://example.com/path/localhost:8000",
        "https://example.com/@localhost",
    ],
)
def test_same_host_detection_is_structural_not_prefix_based(client, url):
    response = create_link(client, url=url)

    assert response.status_code == 201
    assert response.json()["url"] == url


def test_original_url_text_is_preserved(client):
    url = "HTTPS://Example.COM/Mixed/Case?q=1#frag"

    created = create_link(client, url=url).json()

    assert created["url"] == url
    redirect = client.get(f"/{created['code']}")
    assert redirect.status_code == 302
    assert redirect.headers["location"] == url


def test_valid_non_default_port_is_accepted(client):
    url = "https://example.com:8443/path"

    response = create_link(client, url=url)

    assert response.status_code == 201
    assert response.json()["url"] == url


# ---------------------------------------------------------------------------
# FR-5: custom aliases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias", ["abc", "a" * 32, "my_alias-9", "-_-", "Z9_"]
)
def test_valid_custom_aliases_are_honoured(client, alias):
    created = create_link(client, custom_alias=alias)

    assert created.status_code == 201
    assert created.json()["code"] == alias
    assert created.json()["short_url"] == f"{BASE_URL}/{alias}"
    assert client.get(f"/{alias}").status_code == 302


@pytest.mark.parametrize(
    "alias",
    [
        "",
        "ab",
        "a" * 33,
        "dot.name",
        "with space",
        "with/slash",
        "bang!",
        "\u00e9\u00e9\u00e9",
        123,
        True,
        None,
    ],
)
def test_invalid_custom_aliases_return_422(client, alias):
    response = create_link(client, custom_alias=alias)

    error = assert_error(response, 422, "validation_error")
    assert "custom_alias" in error["message"].lower()


@pytest.mark.parametrize(
    "alias",
    ["api", "API", "Api", "docs", "DOCS", "health", "Health", "redoc", "REDOC"],
)
def test_reserved_aliases_are_rejected_case_insensitively(client, alias):
    response = create_link(client, custom_alias=alias)

    error = assert_error(response, 422, "validation_error")
    assert "reserved" in error["message"]


def test_dotted_openapi_alias_is_impossible(client):
    for alias in ("openapi.json", "OpenAPI.JSON"):
        response = create_link(client, custom_alias=alias)
        assert_error(response, 422, "validation_error")


def test_taken_alias_returns_409_and_never_replaces_the_original(client):
    first = create_link(
        client, url="https://example.com/first", custom_alias="dup-alias"
    )
    assert first.status_code == 201

    response = create_link(
        client, url="https://example.com/second", custom_alias="dup-alias"
    )

    assert_error(response, 409, "alias_taken")
    metadata = client.get("/api/links/dup-alias", headers=AUTH).json()
    assert metadata["url"] == "https://example.com/first"
    assert client.get("/dup-alias").headers["location"] == (
        "https://example.com/first"
    )


def test_duplicate_url_with_a_requested_alias_is_created(client):
    first = create_link(client, url="https://example.com/shared")
    assert first.status_code == 201

    second = create_link(
        client, url="https://example.com/shared", custom_alias="shared-alias"
    )

    assert second.status_code == 201
    assert second.json()["code"] == "shared-alias"
    assert first.json()["code"] != "shared-alias"


# ---------------------------------------------------------------------------
# Optional-field strictness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["custom_alias", "expires_at"])
def test_explicit_null_optional_fields_are_rejected(client, field):
    response = create_link(client, **{field: None})

    assert_error(response, 422, "validation_error")


@pytest.mark.parametrize(
    "expires_at",
    [
        "2030-01-01T00:00:00",
        "not-a-timestamp",
        "",
        123,
        True,
        "2030-13-40T99:99:99+00:00",
    ],
)
def test_invalid_expiry_values_are_rejected(client, expires_at):
    response = create_link(client, expires_at=expires_at)

    error = assert_error(response, 422, "validation_error")
    assert "expires_at" in error["message"].lower()


def test_extra_json_fields_are_ignored(client):
    response = client.post(
        "/api/links",
        json={"url": DESTINATION, "unknown": "ignored"},
        headers=AUTH,
    )

    assert response.status_code == 201
    assert response.json()["url"] == DESTINATION


# ---------------------------------------------------------------------------
# FR-11: duplicate URLs
# ---------------------------------------------------------------------------


def test_duplicate_url_without_alias_creates_independent_links(client):
    first = create_link(client, url=EXTERNAL).json()
    second = create_link(client, url=EXTERNAL).json()

    assert first["code"] != second["code"]
    assert first["url"] == second["url"] == EXTERNAL

    assert client.get(f"/{first['code']}").headers["location"] == EXTERNAL
    assert client.get(f"/{second['code']}").headers["location"] == EXTERNAL

    client.get(f"/{first['code']}")

    first_stats = client.get(
        f"/api/links/{first['code']}/stats", headers=AUTH
    ).json()
    second_stats = client.get(
        f"/api/links/{second['code']}/stats", headers=AUTH
    ).json()

    assert first_stats["total_clicks"] == 2
    assert second_stats["total_clicks"] == 1
