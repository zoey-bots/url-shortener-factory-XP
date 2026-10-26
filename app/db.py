"""Per-operation SQLite connections and safe schema bootstrap.

The service is intended to run with several workers against one database
file, therefore every operation opens (and explicitly closes) its own
connection.  WAL mode plus a bounded busy timeout keeps concurrent
readers and short writers from failing spuriously, and the schema is
created with ``IF NOT EXISTS`` inside an immediate transaction so several
processes may start simultaneously.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import sqlite3
import threading

CONNECT_TIMEOUT_SECONDS = 5.0
BUSY_TIMEOUT_MS = 5000

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS links (
        code       TEXT PRIMARY KEY,
        url        TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clicks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        code       TEXT NOT NULL,
        clicked_at TEXT NOT NULL,
        click_date TEXT NOT NULL,
        referrer   TEXT NOT NULL,
        FOREIGN KEY (code) REFERENCES links (code) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_clicks_code ON clicks (code)",
    "CREATE INDEX IF NOT EXISTS idx_clicks_code_date ON clicks (code, click_date)",
    """
    CREATE TABLE IF NOT EXISTS rate_limit_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        key_hash   TEXT NOT NULL,
        created_at REAL NOT NULL
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS idx_rate_limit_key_time "
        "ON rate_limit_events (key_hash, created_at)"
    ),
)


class Database:
    """Owns the database file path and hands out short-lived connections."""

    def __init__(self, path: str) -> None:
        self._uri = path == ":memory:"
        self._anchor: sqlite3.Connection | None = None
        if self._uri:
            # Per-operation connections only share an in-memory database
            # through a named shared cache with one anchor kept open.
            self.path = f"file:urlshortener-{id(self):x}?mode=memory&cache=shared"
        else:
            self.path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._initialized = False

    # -- connections -----------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=CONNECT_TIMEOUT_SECONDS,
            isolation_level=None,  # explicit transaction control below
            uri=self._uri,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection that is always closed when the block exits."""

        self.initialize()
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        """Open a connection wrapped in an explicit transaction."""

        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")
        finally:
            connection.close()

    # -- bootstrap -------------------------------------------------------

    def initialize(self) -> None:
        """Create the schema once per process, safely alongside other workers."""

        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._bootstrap()
            self._initialized = True

    def _bootstrap(self) -> None:
        if self._uri:
            if self._anchor is None:
                self._anchor = sqlite3.connect(
                    self.path,
                    uri=True,
                    isolation_level=None,
                    check_same_thread=False,
                )
        else:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        setup = self._connect()
        try:
            try:
                setup.execute("PRAGMA journal_mode = WAL").fetchone()
            except sqlite3.OperationalError:
                # Another process may hold the lock; the database still works.
                pass

            setup.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA_STATEMENTS:
                    setup.execute(statement)
            except BaseException:
                setup.execute("ROLLBACK")
                raise
            else:
                setup.execute("COMMIT")
        finally:
            setup.close()
