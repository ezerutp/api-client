"""SQLite database for application-wide data (never shared through Git)."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_MIGRATIONS: list[str] = [
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE recent_projects (
        path        TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        last_opened TEXT NOT NULL
    );
    CREATE TABLE history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_path TEXT NOT NULL DEFAULT '',
        timestamp    TEXT NOT NULL,
        method       TEXT NOT NULL,
        url          TEXT NOT NULL,
        status_code  INTEGER,
        elapsed_ms   REAL,
        size_bytes   INTEGER,
        error        TEXT NOT NULL DEFAULT '',
        request_id   TEXT NOT NULL DEFAULT '',
        request_name TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_history_project ON history(project_path, id DESC);
    CREATE TABLE ui_state (
        project_path TEXT PRIMARY KEY,
        state        TEXT NOT NULL
    );
    """,
]


class Database:
    def __init__(self, path: Path | str) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            for index, script in enumerate(_MIGRATIONS[version:], start=version + 1):
                self._connection.executescript(script)
                self._connection.execute(f"PRAGMA user_version = {index}")
            self._connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._connection.close()
