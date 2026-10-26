"""Validation and normalisation helpers for URLs, aliases and timestamps."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = frozenset({"http", "https"})

# Public paths that must stay usable, so they can never become aliases.
RESERVED_ALIASES = frozenset({"api", "docs", "health", "redoc", "openapi.json"})

_ALIAS_PATTERN = re.compile(r"[A-Za-z0-9_-]{3,32}\Z")
_ALIAS_DESCRIPTION = (
    "must be 3-32 characters using ASCII letters, digits, hyphen or underscore"
)


def normalize_hostname(hostname: str) -> str:
    """Case-fold a hostname and drop a single terminal dot."""

    return hostname.rstrip(".").lower()


def hostname_of(value: str) -> str | None:
    """Return the normalised hostname of ``value`` or ``None`` if unusable."""

    try:
        parts = urlsplit(value)
        hostname = parts.hostname
    except ValueError:
        return None
    if not hostname:
        return None
    return normalize_hostname(hostname)


def _has_explicit_empty_port(netloc: str) -> bool:
    """Detect ``host:`` (empty port), which urlsplit tolerates."""

    if netloc.startswith("["):
        closing = netloc.find("]")
        if closing == -1:
            return True
        return netloc[closing + 1 :] == ":"
    return netloc.endswith(":")


def validate_url(value: str) -> str:
    """Validate an absolute HTTP(S) URL, preserving the original text.

    Raises ``ValueError`` with a human-readable message on any problem.
    """

    if not value:
        raise ValueError("must not be empty")

    if len(value) > MAX_URL_LENGTH:
        raise ValueError(f"must be at most {MAX_URL_LENGTH} characters")

    for character in value:
        if character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F:
            raise ValueError("must not contain whitespace or control characters")

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ValueError("must be an absolute URL") from exc

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("must use the http or https scheme")

    if not parts.netloc:
        raise ValueError("must be absolute and include a hostname")

    if "@" in parts.netloc:
        raise ValueError("must not include embedded credentials")

    try:
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ValueError("must include a valid port") from exc

    if port is not None and port == 0:
        raise ValueError("must include a valid port")

    if not hostname or not normalize_hostname(hostname):
        raise ValueError("must include a valid hostname")

    if _has_explicit_empty_port(parts.netloc):
        raise ValueError("must include a valid port")

    return value


def validate_alias(value: str) -> str:
    """Validate a custom alias; raises ``ValueError`` when invalid."""

    if _ALIAS_PATTERN.fullmatch(value) is None:
        raise ValueError(_ALIAS_DESCRIPTION)
    if value.lower() in RESERVED_ALIASES:
        raise ValueError("collides with a reserved path")
    return value


def parse_expires_at(value: str) -> datetime:
    """Parse an ISO8601 timestamp that must carry a timezone offset."""

    text = value.strip()
    if not text:
        raise ValueError("must be a valid ISO8601 timestamp with a timezone offset")

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            "must be a valid ISO8601 timestamp with a timezone offset"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone offset")

    return parsed.astimezone(timezone.utc)


def is_same_hostname(value: str, base_hostname: str) -> bool:
    """Whether ``value`` targets the same normalised host as ``BASE_URL``."""

    candidate = hostname_of(value)
    return candidate is not None and candidate == base_hostname
