"""Shared helpers for the URL shortener test-suite.

The helpers only use the public configuration and HTTP surface of the
application.  Every test gets its own temporary SQLite file, so tests never
depend on the developer's environment, a running server, or the network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings
from app.urls import hostname_of

# Test-only credentials.  They are generated at import time, are never used
# by the application outside the tests, and are never written to a file.
API_KEY = "unit-test-key-primary-4f8d2a"
SECOND_API_KEY = "unit-test-key-secondary-9b1c7e"
BASE_URL = "http://localhost:8000"
DESTINATION = "https://example.com/articles/url-shortener"

AUTH = {"X-API-Key": API_KEY}
SECOND_AUTH = {"X-API-Key": SECOND_API_KEY}


def make_settings(
    database_path: str | Path,
    *,
    base_url: str = BASE_URL,
    api_keys: tuple[str, ...] = (API_KEY,),
) -> Settings:
    """Build explicit settings for an isolated application instance."""

    return Settings(
        base_url=base_url,
        database_path=str(database_path),
        api_keys=tuple(api_keys),
        base_hostname=hostname_of(base_url),
    )


def assert_error(
    response: Any,
    status_code: int,
    code: str | None = None,
) -> dict[str, str]:
    """Assert the canonical ``{"error": {"code", "message"}}`` envelope."""

    assert response.status_code == status_code, response.text
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert isinstance(payload, dict), payload
    assert set(payload) == {"error"}, payload

    error = payload["error"]
    assert isinstance(error, dict), error
    assert set(error) == {"code", "message"}, error
    assert isinstance(error["code"], str) and error["code"].strip(), error
    assert isinstance(error["message"], str) and error["message"].strip(), error
    if code is not None:
        assert error["code"] == code, error
    return error


def create_link(
    client: Any,
    *,
    url: str = DESTINATION,
    headers: dict[str, str] | None = AUTH,
    **fields: Any,
) -> Any:
    """POST a link-creation request, allowing optional fields to be added."""

    body = {"url": url}
    body.update(fields)
    return client.post("/api/links", json=body, headers=headers)
