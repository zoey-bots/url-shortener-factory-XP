"""One consistent JSON error envelope for every non-success response."""

from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_STATUS_TO_CODE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    410: "link_expired",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"


def error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the canonical ``{"error": {"code", "message"}}`` response."""

    safe_code = (code or "").strip() or _STATUS_TO_CODE.get(status_code, "error")
    safe_message = (message or "").strip() or _status_phrase(status_code)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": safe_code, "message": safe_message}},
        headers=headers,
    )


class ApiError(Exception):
    """Domain error carrying the HTTP status and machine-readable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.headers)


async def handle_http_exception(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else ""
    message = detail.strip() or _status_phrase(exc.status_code)
    code = _STATUS_TO_CODE.get(exc.status_code, "error")
    headers = getattr(exc, "headers", None)
    return error_response(exc.status_code, code, message, headers)


async def handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    message = "Invalid request."
    errors = exc.errors()
    if errors:
        first = errors[0]
        location = ".".join(
            str(part)
            for part in first.get("loc", ())
            if part not in ("body", "query", "header", "path")
        )
        detail = str(first.get("msg") or "").strip()
        if detail.startswith("Value error, "):
            detail = detail[len("Value error, ") :]
        if location and detail:
            message = f"{location}: {detail}"
        elif detail:
            message = detail
    return error_response(422, "validation_error", message)


async def handle_unexpected(_: Request, __: Exception) -> JSONResponse:
    return error_response(500, "internal_error", "Internal server error.")


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers so every failure path uses the error envelope."""

    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected)
