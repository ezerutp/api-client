"""``.secrets.json``: values that must not be committed.

Format (both layouts can be mixed)::

    {
      "token": "global secret, available in every environment",
      "local":      {"token": "secret only for the local environment"},
      "production": {"password": "..."}
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.repositories.project_repository import SECRETS_FILE
from app.storage.json_file import JsonFileError, read_json, write_json_atomic


@dataclass
class Secrets:
    globals: dict[str, str] = field(default_factory=dict)
    by_environment: dict[str, dict[str, str]] = field(default_factory=dict)

    def for_environment(self, name: str | None) -> dict[str, str]:
        return dict(self.by_environment.get(name or "", {}))

    def all_values(self) -> set[str]:
        values = set(self.globals.values())
        for env in self.by_environment.values():
            values.update(env.values())
        return {v for v in values if v}

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = dict(self.globals)
        for env_name, values in self.by_environment.items():
            if values:
                data[env_name] = dict(values)
        return data

    @classmethod
    def from_dict(cls, raw: object) -> Secrets:
        secrets = cls()
        if not isinstance(raw, dict):
            return secrets
        for key, value in raw.items():
            if isinstance(value, dict):
                secrets.by_environment[str(key)] = {str(k): str(v) for k, v in value.items() if v is not None}
            elif value is not None:
                secrets.globals[str(key)] = str(value)
        return secrets


class SecretsRepository:
    def __init__(self, api_dir: Path) -> None:
        self.path = api_dir / SECRETS_FILE

    def load(self) -> tuple[Secrets, str | None]:
        """Returns the secrets and, if the file is corrupt, a readable warning."""
        if not self.path.exists():
            return Secrets(), None
        try:
            return Secrets.from_dict(read_json(self.path)), None
        except JsonFileError as exc:
            if exc.message == "file is empty":
                return Secrets(), None
            return Secrets(), f"{SECRETS_FILE}: {exc.message}"

    def save(self, secrets: Secrets) -> None:
        write_json_atomic(self.path, secrets.to_dict())
