"""API-key authentication helpers.

Keys are compared in constant time across every configured key (no early
exit on the first match) and only a SHA-256 digest of the key is ever
persisted, as the rate-limiter identity.
"""

from __future__ import annotations

import hashlib
import hmac

from .config import Settings

API_PREFIX = "/api"


def is_api_path(path: str) -> bool:
    """Whether ``path`` belongs to the authenticated ``/api`` surface."""

    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


def hash_key(key: str) -> str:
    """Stable, one-way identity for an API key."""

    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def authenticate(settings: Settings, provided: str | None) -> str | None:
    """Return the key hash for a valid key, or ``None`` when unauthorised."""

    if not provided or not settings.api_keys:
        return None

    provided_bytes = provided.encode("utf-8")
    matched = False
    for candidate in settings.api_keys:
        if hmac.compare_digest(candidate.encode("utf-8"), provided_bytes):
            matched = True

    return hash_key(provided) if matched else None
