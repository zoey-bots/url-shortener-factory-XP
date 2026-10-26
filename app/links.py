"""Persistence for links, redirects, clicks and statistics.

Duplicate policy: submitting an original URL that is already shortened
without a ``custom_alias`` always creates a fresh random code (the short
links are independent and each keeps its own analytics).  A requested
alias is always honoured exactly, never silently replaced.

Every method uses a short-lived connection; writes use explicit
transactions so concurrent workers and the delete/redirect race behave
deterministically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any

from .codes import generate_code
from .db import Database
from .errors import ApiError

MAX_CODE_ATTEMPTS = 10
STATS_DAYS = 7
TOP_REFERRERS = 5
DIRECT_REFERRER = "direct"

_LINK_COLUMNS = "code, url, created_at, expires_at"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_referrer(value: str | None) -> str:
    """Missing/blank ``Referer`` values are bucketed as ``direct``."""

    if value is None:
        return DIRECT_REFERRER
    cleaned = value.strip()
    return cleaned or DIRECT_REFERRER


def _is_expired(expires_at: str | None, now: datetime) -> bool:
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) <= now.astimezone(timezone.utc)


class LinkRepository:
    """All database operations needed by the HTTP layer."""

    def __init__(self, db: Database, base_url: str) -> None:
        self._db = db
        self._prefix = base_url.rstrip("/")

    # -- serialisation ---------------------------------------------------

    def _serialize(self, row: sqlite3.Row) -> dict[str, Any]:
        code = row["code"]
        return {
            "code": code,
            "short_url": f"{self._prefix}/{code}",
            "url": row["url"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    # -- creation --------------------------------------------------------

    def create(
        self,
        url: str,
        custom_alias: str | None = None,
        expires_at: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        created_at = (now or utc_now()).astimezone(timezone.utc).isoformat()

        if custom_alias is not None:
            try:
                return self._insert(custom_alias, url, created_at, expires_at)
            except sqlite3.IntegrityError as exc:
                raise ApiError(
                    409,
                    "alias_taken",
                    "The requested custom alias is already in use.",
                ) from exc

        for _ in range(MAX_CODE_ATTEMPTS):
            try:
                return self._insert(generate_code(), url, created_at, expires_at)
            except sqlite3.IntegrityError:
                continue

        raise ApiError(
            500,
            "code_generation_failed",
            "Unable to allocate a unique short code.",
        )

    def _insert(
        self,
        code: str,
        url: str,
        created_at: str,
        expires_at: str | None,
    ) -> dict[str, Any]:
        with self._db.transaction(immediate=True) as connection:
            connection.execute(
                f"INSERT INTO links ({_LINK_COLUMNS}) VALUES (?, ?, ?, ?)",
                (code, url, created_at, expires_at),
            )
            row = connection.execute(
                f"SELECT {_LINK_COLUMNS} FROM links WHERE code = ?", (code,)
            ).fetchone()
        return self._serialize(row)

    # -- reads -----------------------------------------------------------

    def get(self, code: str) -> dict[str, Any] | None:
        with self._db.connect() as connection:
            row = connection.execute(
                f"SELECT {_LINK_COLUMNS} FROM links WHERE code = ?", (code,)
            ).fetchone()
        return None if row is None else self._serialize(row)

    # -- deletion --------------------------------------------------------

    def delete(self, code: str) -> bool:
        with self._db.transaction(immediate=True) as connection:
            connection.execute("DELETE FROM clicks WHERE code = ?", (code,))
            result = connection.execute(
                "DELETE FROM links WHERE code = ?", (code,)
            )
            deleted = result.rowcount > 0
        return deleted

    # -- redirect + click -------------------------------------------------

    def resolve(
        self,
        code: str,
        referrer: str,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any] | None, int]:
        """Resolve a code for redirecting.

        Returns ``(link, 302)`` on success, ``(None, 404)`` for an unknown
        code and ``(link, 410)`` for an expired one.  The lookup, expiry
        check and click insertion all run under the same immediate write
        lock, so a concurrent delete/recreate of the alias cannot redirect
        to the old URL while charging the click to its replacement.
        """

        current = (now or utc_now()).astimezone(timezone.utc)

        with self._db.transaction(immediate=True) as connection:
            row = connection.execute(
                f"SELECT {_LINK_COLUMNS} FROM links WHERE code = ?", (code,)
            ).fetchone()
            if row is None:
                return None, 404

            link = self._serialize(row)
            if _is_expired(row["expires_at"], current):
                return link, 410

            connection.execute(
                "INSERT INTO clicks (code, clicked_at, click_date, referrer) "
                "VALUES (?, ?, ?, ?)",
                (
                    code,
                    current.isoformat(),
                    current.date().isoformat(),
                    referrer,
                ),
            )

        return link, 302

    # -- analytics -------------------------------------------------------

    def stats(
        self, code: str, now: datetime | None = None
    ) -> dict[str, Any] | None:
        """Return analytics for ``code`` or ``None`` when it does not exist."""

        current = (now or utc_now()).astimezone(timezone.utc)
        today = current.date()
        first_day = today - timedelta(days=STATS_DAYS - 1)

        with self._db.transaction(immediate=False) as connection:
            exists = connection.execute(
                "SELECT 1 FROM links WHERE code = ?", (code,)
            ).fetchone()
            if exists is None:
                return None

            total = connection.execute(
                "SELECT COUNT(*) AS total FROM clicks WHERE code = ?", (code,)
            ).fetchone()["total"]

            daily_rows = connection.execute(
                "SELECT click_date, COUNT(*) AS total FROM clicks "
                "WHERE code = ? AND click_date >= ? GROUP BY click_date",
                (code, first_day.isoformat()),
            ).fetchall()

            top_rows = connection.execute(
                "SELECT referrer, COUNT(*) AS total FROM clicks "
                "WHERE code = ? GROUP BY referrer "
                "ORDER BY total DESC, referrer ASC LIMIT ?",
                (code, TOP_REFERRERS),
            ).fetchall()

        daily_counts = {
            row["click_date"]: int(row["total"]) for row in daily_rows
        }
        clicks_per_day = [
            {
                "date": (first_day + timedelta(days=offset)).isoformat(),
                "clicks": daily_counts.get(
                    (first_day + timedelta(days=offset)).isoformat(), 0
                ),
            }
            for offset in range(STATS_DAYS)
        ]

        return {
            "total_clicks": int(total),
            "clicks_per_day": clicks_per_day,
            "top_referrers": [
                {"referrer": row["referrer"], "clicks": int(row["total"])}
                for row in top_rows
            ],
        }
