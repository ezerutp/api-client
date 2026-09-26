"""Per-project UI state (open tabs, splitters, environment). Local to this machine."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from app.storage.database import Database


@dataclass
class ProjectUiState:
    open_request_ids: list[str] = field(default_factory=list)
    active_request_id: str | None = None
    environment: str | None = None
    collapsed_collections: list[str] = field(default_factory=list)
    sidebar_width: int = 260
    editor_split: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: object) -> ProjectUiState:
        state = cls()
        if not isinstance(raw, dict):
            return state
        if isinstance(raw.get("open_request_ids"), list):
            state.open_request_ids = [str(x) for x in raw["open_request_ids"]]
        if isinstance(raw.get("active_request_id"), str):
            state.active_request_id = raw["active_request_id"]
        if isinstance(raw.get("environment"), str):
            state.environment = raw["environment"]
        if isinstance(raw.get("collapsed_collections"), list):
            state.collapsed_collections = [str(x) for x in raw["collapsed_collections"]]
        if isinstance(raw.get("sidebar_width"), int):
            state.sidebar_width = raw["sidebar_width"]
        split = raw.get("editor_split")
        if isinstance(split, list) and all(isinstance(x, int) for x in split):
            state.editor_split = split
        return state


class UiStateRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def load(self, project_path: str) -> ProjectUiState:
        rows = self._db.query("SELECT state FROM ui_state WHERE project_path = ?", (project_path,))
        if not rows:
            return ProjectUiState()
        try:
            return ProjectUiState.from_dict(json.loads(rows[0]["state"]))
        except ValueError:
            return ProjectUiState()

    def save(self, project_path: str, state: ProjectUiState) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO ui_state(project_path, state) VALUES(?, ?) "
                "ON CONFLICT(project_path) DO UPDATE SET state = excluded.state",
                (project_path, json.dumps(asdict(state))),
            )
