"""FR-10 unit tests: atomic, persistent, per-key rolling-window limiting."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.auth import hash_key
from app.db import Database
from app.errors import ApiError
from app import ratelimit
from tests.support import API_KEY


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(str(tmp_path / "links.db"))
    database.initialize()
    return database


def test_limit_allows_exactly_max_requests_then_returns_429(db, monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_REQUESTS", 3)
    monkeypatch.setattr(ratelimit, "WINDOW_SECONDS", 10.0)
    key = hash_key(API_KEY)

    for _ in range(3):
        ratelimit.enforce_limit(db, key, now=100.0)

    with pytest.raises(ApiError) as excinfo:
        ratelimit.enforce_limit(db, key, now=100.5)

    assert excinfo.value.status_code == 429
    assert excinfo.value.code == "rate_limited"
    assert excinfo.value.headers == {"Retry-After": "10"}


def test_retry_after_is_at_least_one_second(db, monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_REQUESTS", 1)
    monkeypatch.setattr(ratelimit, "WINDOW_SECONDS", 10.0)
    key = hash_key(API_KEY)
    ratelimit.enforce_limit(db, key, now=100.0)

    with pytest.raises(ApiError) as excinfo:
        ratelimit.enforce_limit(db, key, now=109.9)

    assert excinfo.value.headers == {"Retry-After": "1"}


def test_window_slides_and_old_events_are_discarded(db, monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_REQUESTS", 2)
    monkeypatch.setattr(ratelimit, "WINDOW_SECONDS", 10.0)
    key = hash_key(API_KEY)
    ratelimit.enforce_limit(db, key, now=100.0)
    ratelimit.enforce_limit(db, key, now=100.0)

    with pytest.raises(ApiError):
        ratelimit.enforce_limit(db, key, now=105.0)

    # Both earlier events fall outside the window exactly at now - window.
    ratelimit.enforce_limit(db, key, now=110.0)
    ratelimit.enforce_limit(db, key, now=110.0)


def test_each_key_has_an_independent_budget(db, monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_REQUESTS", 2)
    monkeypatch.setattr(ratelimit, "WINDOW_SECONDS", 60.0)
    first = hash_key(API_KEY)
    second = hash_key("another-test-key")

    ratelimit.enforce_limit(db, first, now=100.0)
    ratelimit.enforce_limit(db, first, now=100.0)
    with pytest.raises(ApiError):
        ratelimit.enforce_limit(db, first, now=100.0)

    ratelimit.enforce_limit(db, second, now=100.0)


def test_limit_survives_a_process_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_REQUESTS", 2)
    monkeypatch.setattr(ratelimit, "WINDOW_SECONDS", 60.0)
    path = str(tmp_path / "persistent.db")
    key = hash_key(API_KEY)

    first = Database(path)
    ratelimit.enforce_limit(first, key, now=100.0)
    ratelimit.enforce_limit(first, key, now=100.0)

    second = Database(path)
    with pytest.raises(ApiError):
        ratelimit.enforce_limit(second, key, now=100.0)


def test_only_the_hashed_key_identity_is_stored(db, monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_REQUESTS", 2)
    key = hash_key(API_KEY)
    ratelimit.enforce_limit(db, key, now=100.0)

    with db.connect() as connection:
        rows = connection.execute(
            "SELECT key_hash FROM rate_limit_events"
        ).fetchall()

    assert [row["key_hash"] for row in rows] == [key]
    assert API_KEY not in str([row["key_hash"] for row in rows])


def test_concurrent_workers_cannot_overshoot_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_REQUESTS", 5)
    monkeypatch.setattr(ratelimit, "WINDOW_SECONDS", 60.0)
    path = str(tmp_path / "atomic.db")
    databases = [Database(path) for _ in range(20)]
    for database in databases:
        database.initialize()

    def attempt(database: Database) -> bool:
        try:
            ratelimit.enforce_limit(database, "shared-key", now=500.0)
        except ApiError as exc:
            assert exc.status_code == 429
            return False
        return True

    with ThreadPoolExecutor(max_workers=10) as pool:
        allowed = list(pool.map(attempt, databases))

    assert sum(allowed) == 5
    assert len(allowed) == 20
