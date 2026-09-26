from __future__ import annotations

from app.models.history import HistoryEntry
from app.storage.database import Database

_COLUMNS = "id, project_path, timestamp, method, url, status_code, elapsed_ms, size_bytes, error, request_id, request_name"


class HistoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, entry: HistoryEntry, keep_last: int = 500) -> None:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO history(project_path, timestamp, method, url, status_code, elapsed_ms, size_bytes, "
                "error, request_id, request_name) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.project_path, entry.timestamp, entry.method, entry.url, entry.status_code,
                    entry.elapsed_ms, entry.size_bytes, entry.error, entry.request_id, entry.request_name,
                ),
            )
            entry.id = cursor.lastrowid
            conn.execute(
                "DELETE FROM history WHERE project_path = ? AND id NOT IN "
                "(SELECT id FROM history WHERE project_path = ? ORDER BY id DESC LIMIT ?)",
                (entry.project_path, entry.project_path, keep_last),
            )

    def list(self, project_path: str, limit: int = 500) -> list[HistoryEntry]:
        rows = self._db.query(
            f"SELECT {_COLUMNS} FROM history WHERE project_path = ? ORDER BY id DESC LIMIT ?",
            (project_path, limit),
        )
        return [
            HistoryEntry(
                id=r["id"], project_path=r["project_path"], timestamp=r["timestamp"], method=r["method"],
                url=r["url"], status_code=r["status_code"], elapsed_ms=r["elapsed_ms"],
                size_bytes=r["size_bytes"], error=r["error"], request_id=r["request_id"],
                request_name=r["request_name"],
            )
            for r in rows
        ]

    def clear(self, project_path: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM history WHERE project_path = ?", (project_path,))
