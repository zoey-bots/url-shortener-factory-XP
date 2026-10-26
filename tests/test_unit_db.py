"""SQLite infrastructure unit tests: schema, WAL, close and persistence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3

import pytest

from app.db import BUSY_TIMEOUT_MS, CONNECT_TIMEOUT_SECONDS, Database


def _table_names(database: Database) -> set[str]:
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row["name"] for row in rows}


def test_file_path_is_made_absolute(tmp_path):
    database = Database(str(tmp_path / "nested" / "links.db"))

    assert os.path.isabs(database.path)
    assert database.path.endswith("links.db")


def test_initialize_creates_schema_and_parent_directory(tmp_path):
    database = Database(str(tmp_path / "nested" / "links.db"))

    database.initialize()

    assert (tmp_path / "nested").is_dir()
    assert _table_names(database) >= {"links", "clicks", "rate_limit_events"}


def test_initialize_is_idempotent(tmp_path):
    database = Database(str(tmp_path / "links.db"))

    database.initialize()
    database.initialize()

    assert "links" in _table_names(database)


def test_connections_use_wal_bounded_timeout_and_foreign_keys(tmp_path):
    database = Database(str(tmp_path / "links.db"))

    with database.connect() as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert int(busy_timeout) == BUSY_TIMEOUT_MS == 5000
    assert int(foreign_keys) == 1
    assert CONNECT_TIMEOUT_SECONDS == 5.0


def test_connect_explicitly_closes_the_connection(tmp_path):
    database = Database(str(tmp_path / "links.db"))

    with database.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_transaction_commits_on_success(tmp_path):
    database = Database(str(tmp_path / "links.db"))

    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO rate_limit_events (key_hash, created_at) VALUES (?, ?)",
            ("commit-key", 1.0),
        )

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM rate_limit_events WHERE key_hash = ?",
            ("commit-key",),
        ).fetchone()[0]

    assert count == 1


def test_transaction_rolls_back_on_exception(tmp_path):
    database = Database(str(tmp_path / "links.db"))

    with pytest.raises(RuntimeError):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO rate_limit_events (key_hash, created_at) "
                "VALUES (?, ?)",
                ("rollback-key", 1.0),
            )
            raise RuntimeError("boom")

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM rate_limit_events WHERE key_hash = ?",
            ("rollback-key",),
        ).fetchone()[0]

    assert count == 0


def test_a_new_database_instance_reopens_the_same_file(tmp_path):
    path = str(tmp_path / "links.db")
    first = Database(path)
    with first.transaction() as connection:
        connection.execute(
            "INSERT INTO rate_limit_events (key_hash, created_at) VALUES (?, ?)",
            ("persisted-key", 2.0),
        )

    second = Database(path)
    with second.connect() as connection:
        row = connection.execute(
            "SELECT key_hash FROM rate_limit_events"
        ).fetchone()

    assert row["key_hash"] == "persisted-key"


def test_simultaneous_schema_bootstrap_is_safe(tmp_path):
    path = str(tmp_path / "links.db")
    databases = [Database(path) for _ in range(8)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda database: database.initialize(), databases))

    assert "links" in _table_names(databases[0])


def test_in_memory_database_shares_one_cache_across_connections():
    database = Database(":memory:")
    database.initialize()

    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO rate_limit_events (key_hash, created_at) VALUES (?, ?)",
            ("memory-key", 3.0),
        )

    with database.connect() as connection:
        row = connection.execute(
            "SELECT key_hash FROM rate_limit_events"
        ).fetchone()

    assert row["key_hash"] == "memory-key"
