"""Consistent JSON error envelope unit tests."""

from __future__ import annotations

import asyncio
import json

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    ApiError,
    error_response,
    handle_api_error,
    handle_http_exception,
    handle_unexpected,
    handle_validation_error,
)


def _payload(response) -> dict:
    return json.loads(response.body)


def test_error_response_uses_the_canonical_envelope():
    response = error_response(404, "not_found", "Short link not found.")
    body = _payload(response)

    assert response.status_code == 404
    assert body == {
        "error": {"code": "not_found", "message": "Short link not found."}
    }
    assert response.headers["content-type"].startswith("application/json")


def test_error_response_fills_blank_values_with_nonblank_defaults():
    body = _payload(error_response(401, "", ""))

    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"] == "Unauthorized"


def test_error_response_falls_back_for_unmapped_status():
    body = _payload(error_response(418, "", ""))

    assert body["error"]["code"] == "error"
    assert body["error"]["message"] == "I'm a Teapot"


def test_error_response_preserves_headers():
    response = error_response(
        429, "rate_limited", "Too many", headers={"Retry-After": "7"}
    )

    assert response.headers["retry-after"] == "7"


def test_api_error_carries_status_code_and_headers():
    error = ApiError(429, "rate_limited", "Too many", {"Retry-After": "3"})

    assert error.status_code == 429
    assert error.code == "rate_limited"
    assert error.message == "Too many"
    assert error.headers == {"Retry-After": "3"}
    assert str(error) == "Too many"


def test_handle_api_error_builds_envelope():
    response = asyncio.run(
        handle_api_error(None, ApiError(410, "link_expired", "Expired."))
    )

    assert response.status_code == 410
    assert _payload(response) == {
        "error": {"code": "link_expired", "message": "Expired."}
    }


def test_handle_http_exception_maps_status_to_machine_code():
    response = asyncio.run(
        handle_http_exception(None, StarletteHTTPException(405, "Nope"))
    )

    assert response.status_code == 405
    assert _payload(response)["error"] == {
        "code": "method_not_allowed",
        "message": "Nope",
    }


def test_handle_validation_error_summarises_the_first_field():
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "url"),
                    "msg": "Value error, must use the http or https scheme",
                "type": "value_error",
            }
        ]
    )

    response = asyncio.run(handle_validation_error(None, exc))
    error = _payload(response)["error"]

    assert response.status_code == 422
    assert error["code"] == "validation_error"
    assert error["message"] == "url: must use the http or https scheme"


def test_handle_unexpected_hides_internal_details():
    response = asyncio.run(handle_unexpected(None, RuntimeError("secret detail")))
    body = _payload(response)

    assert response.status_code == 500
    assert body == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert "secret detail" not in str(body)
