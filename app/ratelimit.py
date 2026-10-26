"""Atomic, persistent, rolling-window rate limiting in SQLite.

Each allowed request appends a timestamp row and each check first drops
events older than the window.  The whole check-and-insert runs inside a
single ``BEGIN IMMEDIATE`` transaction, so simultaneous requests from
different threads or worker processes cannot overshoot the limit.  State
lives in the database, so a process restart never resets the window.
"""

from __future__ import annotations

import math
import time

from .db import Database
from .errors import ApiError

MAX_REQUESTS = 60
WINDOW_SECONDS = 60.0


def enforce_limit(db: Database, key_hash: str, now: float | None = None) -> None:
    """Consume one slot for ``key_hash`` or raise a 429 ``ApiError``."""

    current = time.time() if now is None else now
    cutoff = current - WINDOW_SECONDS

    with db.transaction(immediate=True) as connection:
        connection.execute(
            "DELETE FROM rate_limit_events WHERE key_hash = ? AND created_at <= ?",
            (key_hash, cutoff),
        )
        row = connection.execute(
            "SELECT COUNT(*) AS total, MIN(created_at) AS oldest "
            "FROM rate_limit_events WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()

        total = int(row["total"])
        if total >= MAX_REQUESTS:
            oldest = row["oldest"]
            retry_after = 1
            if oldest is not None:
                remaining = (float(oldest) + WINDOW_SECONDS) - current
                retry_after = max(1, math.ceil(remaining))
            raise ApiError(
                429,
                "rate_limited",
                "Rate limit exceeded. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        connection.execute(
            "INSERT INTO rate_limit_events (key_hash, created_at) VALUES (?, ?)",
            (key_hash, current),
        )
