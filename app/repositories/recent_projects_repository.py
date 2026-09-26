from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.storage.database import Database


@dataclass(frozen=True)
class RecentProject:
    path: str
    name: str
    last_opened: datetime


class RecentProjectsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def touch(self, path: str, name: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO recent_projects(path, name, last_opened) VALUES(?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET name = excluded.name, last_opened = excluded.last_opened",
                (path, name, datetime.now().isoformat(timespec="seconds")),
            )

    def list(self, limit: int = 10) -> list[RecentProject]:
        rows = self._db.query(
            "SELECT path, name, last_opened FROM recent_projects ORDER BY last_opened DESC LIMIT ?", (limit,)
        )
        return [RecentProject(r["path"], r["name"], datetime.fromisoformat(r["last_opened"])) for r in rows]

    def remove(self, path: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM recent_projects WHERE path = ?", (path,))
