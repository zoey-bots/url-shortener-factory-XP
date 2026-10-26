"""Environment-driven configuration.

Exactly three environment variables are supported: ``BASE_URL``,
``DATABASE_PATH`` and ``API_KEYS``.  ``API_KEYS`` is a comma-separated
list of keys; surrounding whitespace is trimmed and empty entries are
ignored.  An empty key list fails closed (every ``/api/*`` request is
rejected) rather than opening the API up.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os

from .urls import hostname_of

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_DATABASE_PATH = "./links.db"


@dataclass(frozen=True)
class Settings:
    """Resolved, immutable runtime configuration."""

    base_url: str
    database_path: str
    api_keys: tuple[str, ...]
    base_hostname: str | None

    @property
    def short_url_prefix(self) -> str:
        """``BASE_URL`` without a trailing slash, used to build short URLs."""
        return self.base_url.rstrip("/")

    def short_url(self, code: str) -> str:
        return f"{self.short_url_prefix}/{code}"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from the process environment (or a supplied mapping)."""

    source = os.environ if env is None else env

    base_url = (source.get("BASE_URL") or "").strip() or DEFAULT_BASE_URL
    database_path = (source.get("DATABASE_PATH") or "").strip() or DEFAULT_DATABASE_PATH

    raw_keys = source.get("API_KEYS") or ""
    api_keys = tuple(part.strip() for part in raw_keys.split(",") if part.strip())

    return Settings(
        base_url=base_url,
        database_path=database_path,
        api_keys=api_keys,
        base_hostname=hostname_of(base_url),
    )
