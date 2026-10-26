"""Public endpoints: health check and short-code redirects."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from .errors import ApiError
from .links import normalize_referrer

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/{code}")
def redirect(code: str, request: Request) -> RedirectResponse:
    """Resolve a short code and redirect to the original URL.

    Clicks are recorded only for a successful redirect.  Expired links
    return 410 and unknown codes return 404 without touching analytics.
    """

    referer = request.headers.get("referer") or request.headers.get("referrer")
    link, status_code = request.app.state.repository.resolve(
        code, normalize_referrer(referer)
    )

    if status_code == 404 or link is None:
        raise ApiError(404, "not_found", "Short link not found.")
    if status_code == 410:
        raise ApiError(410, "link_expired", "Short link has expired.")

    return RedirectResponse(url=link["url"], status_code=302)
