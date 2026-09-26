from __future__ import annotations

import json
from typing import Any

from app.models.settings import AppSettings
from app.storage.database import Database

_SETTINGS_KEY = "app_settings"


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, key: str, default: Any = None) -> Any:
        rows = self._db.query("SELECT value FROM settings WHERE key = ?", (key,))
        if not rows:
            return default
        try:
            return json.loads(rows[0]["value"])
        except ValueError:
            return default

    def set(self, key: str, value: Any) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def load(self) -> AppSettings:
        raw = self.get(_SETTINGS_KEY, {})
        return AppSettings.from_dict(raw if isinstance(raw, dict) else {})

    def save(self, settings: AppSettings) -> None:
        self.set(_SETTINGS_KEY, settings.to_dict())
