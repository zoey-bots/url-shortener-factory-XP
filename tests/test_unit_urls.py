"""FR-4/FR-5 unit tests: URL, hostname, alias and timestamp validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.urls import (
    is_same_hostname,
    hostname_of,
    normalize_hostname,
    parse_expires_at,
    validate_alias,
    validate_url,
)

BASE_URL_LENGTH = len("https://example.com/")


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "http://example.com/path?q=1#fragment",
        "HTTPS://Example.COM/Path",
        "https://example.com:8443/x",
        "https://127.0.0.1/x",
        "https://example.com/@user",
        "https://sub.example.com/a%20b?x=%2F",
        "https://example.com/?next=http://localhost:8000/abc",
    ],
)
def test_validate_url_accepts_absolute_http_urls_and_preserves_text(value):
    assert validate_url(value) == value


def test_validate_url_accepts_exactly_2048_characters():
    value = "https://example.com/" + "a" * (2048 - BASE_URL_LENGTH)
    assert len(value) == 2048
    assert validate_url(value) == value


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("", "empty"),
        ("ftp://example.com/x", "http or https"),
        ("file:///etc/passwd", "http or https"),
        ("//example.com/x", "http or https"),
        ("not-a-url", "http or https"),
        ("https://", "absolute"),
        ("https:///path", "absolute"),
        ("https://[::1", "absolute"),
        ("https://user:secret@example.com/x", "credentials"),
        ("https://user@example.com/x", "credentials"),
        ("https://exa mple.com/x", "whitespace"),
        ("https://example.com/a\tb", "whitespace"),
        ("https://example.com/\x00", "control"),
        ("https://example.com/\x7f", "control"),
        ("https://example.com:", "valid port"),
        ("https://example.com:0", "valid port"),
        ("https://example.com:65536", "valid port"),
        ("https://example.com:notaport", "valid port"),
    ],
)
def test_validate_url_rejects_invalid_input(value, reason):
    with pytest.raises(ValueError) as excinfo:
        validate_url(value)

    assert reason in str(excinfo.value)


def test_validate_url_rejects_2049_characters():
    value = "https://example.com/" + "a" * (2049 - BASE_URL_LENGTH)
    assert len(value) == 2049

    with pytest.raises(ValueError) as excinfo:
        validate_url(value)

    assert "2048" in str(excinfo.value)


@pytest.mark.parametrize(
    ("hostname", "expected"),
    [
        ("Example.COM.", "example.com"),
        ("localhost.", "localhost"),
        ("LOCALHOST", "localhost"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
    ],
)
def test_normalize_hostname_casefolds_and_strips_one_terminal_dot(
    hostname, expected
):
    assert normalize_hostname(hostname) == expected


def test_hostname_of_uses_structural_parsing():
    assert hostname_of("https://User@Example.com.:8080/path") == "example.com"
    assert hostname_of("not a url") is None
    assert hostname_of("https://") is None


def test_is_same_hostname_ignores_case_terminal_dot_and_port():
    assert is_same_hostname("http://LOCALHOST.:9999/abc", "localhost")
    assert is_same_hostname("https://localhost/abc", "localhost")
    assert not is_same_hostname("https://example.com/abc", "localhost")
    assert not is_same_hostname("not a url", "localhost")


@pytest.mark.parametrize("alias", ["abc", "a_b-9", "-_-", "A" * 32])
def test_validate_alias_accepts_three_to_thirty_two_ascii_characters(alias):
    assert validate_alias(alias) == alias


@pytest.mark.parametrize(
    "alias",
    [
        "",
        "ab",
        "a" * 33,
        "has space",
        "dot.name",
        "with/slash",
        "bang!",
        "\u00e9\u00e9\u00e9",
    ],
)
def test_validate_alias_rejects_bad_lengths_or_characters(alias):
    with pytest.raises(ValueError):
        validate_alias(alias)


@pytest.mark.parametrize(
    "alias", ["api", "API", "Api", "docs", "DOCS", "health", "Health", "redoc"]
)
def test_validate_alias_reserves_public_paths_case_insensitively(alias):
    with pytest.raises(ValueError) as excinfo:
        validate_alias(alias)

    assert "reserved" in str(excinfo.value)


@pytest.mark.parametrize("alias", ["openapi.json", "OpenAPI.JSON"])
def test_validate_alias_rejects_the_dotted_openapi_path(alias):
    # The dot is not allowed by the character class, so this can never be
    # created even before the reserved-name comparison is reached.
    with pytest.raises(ValueError):
        validate_alias(alias)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-02T03:04:05+00:00", "2026-01-02T03:04:05+00:00"),
        ("2026-01-02T03:04:05Z", "2026-01-02T03:04:05+00:00"),
        ("2026-01-02T03:04:05+02:00", "2026-01-02T01:04:05+00:00"),
        ("  2026-01-02T03:04:05Z  ", "2026-01-02T03:04:05+00:00"),
    ],
)
def test_parse_expires_at_accepts_timezone_aware_iso8601(value, expected):
    parsed = parse_expires_at(value)

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.astimezone(timezone.utc).isoformat() == expected


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("", "timezone offset"),
        ("   ", "timezone offset"),
        ("not-a-timestamp", "ISO8601"),
        ("2026-13-40T99:99:99+00:00", "ISO8601"),
        ("2026-01-02T03:04:05", "timezone offset"),
    ],
)
def test_parse_expires_at_rejects_naive_or_invalid_values(value, reason):
    with pytest.raises(ValueError) as excinfo:
        parse_expires_at(value)

    assert reason in str(excinfo.value)


def test_parse_expires_at_is_datetime_compatible():
    parsed = parse_expires_at("2026-01-02T03:04:05Z")

    assert isinstance(parsed, datetime)
    assert parsed == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
