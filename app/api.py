"""Authenticated JSON API under ``/api``.

Authentication itself happens in middleware (so unknown ``/api/*`` paths
are protected too); the rate limiter is a per-route dependency so only
link creation consumes quota.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from .auth import authenticate
from .errors import ApiError
from .ratelimit import enforce_limit
from .schemas import CreateLinkRequest
from .urls import is_same_hostname

router = APIRouter(prefix="/api")


def _rate_limit(request: Request) -> None:
    """Consume one creation slot for the authenticated key.

    The middleware has already rejected unauthenticated calls; the key is
    looked up again here so the dependency owns its own identity and does
    not rely on shared middleware state.
    """

    key_hash = authenticate(
        request.app.state.settings, request.headers.get("x-api-key")
    )
    if key_hash is None:
        raise ApiError(401, "unauthorized", "Missing or invalid API key.")
    enforce_limit(request.app.state.db, key_hash)


@router.post("/links", status_code=201)
def create_link(
    payload: CreateLinkRequest,
    request: Request,
    _: None = Depends(_rate_limit),
) -> dict:
    settings = request.app.state.settings
    if settings.base_hostname and is_same_hostname(
        payload.url, settings.base_hostname
    ):
        raise ApiError(
            422,
            "validation_error",
            "url: must not point back to this service",
        )

    return request.app.state.repository.create(
        url=payload.url,
        custom_alias=payload.custom_alias,
        expires_at=payload.expires_at,
    )


@router.get("/links/{code}")
def get_link(code: str, request: Request) -> dict:
    link = request.app.state.repository.get(code)
    if link is None:
        raise ApiError(404, "not_found", "Short link not found.")
    return link


@router.delete("/links/{code}", status_code=204)
def delete_link(code: str, request: Request) -> Response:
    if not request.app.state.repository.delete(code):
        raise ApiError(404, "not_found", "Short link not found.")
    return Response(status_code=204)


@router.get("/links/{code}/stats")
def get_stats(code: str, request: Request) -> dict:
    stats = request.app.state.repository.stats(code)
    if stats is None:
        raise ApiError(404, "not_found", "Short link not found.")
    return stats
