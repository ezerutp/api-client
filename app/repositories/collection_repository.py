from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.models.collection import Collection
from app.repositories.project_repository import PROJECT_FILE
from app.storage.json_file import JsonFileError, read_json, write_json_atomic

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionLoadWarning:
    file_name: str
    message: str


class CollectionRepository:
    """One JSON file per collection, directly inside ``api-client/``."""

    def __init__(self, api_dir: Path) -> None:
        self.api_dir = api_dir

    def path_for(self, collection_id: str) -> Path:
        return self.api_dir / f"{collection_id}.json"

    def collection_files(self) -> list[Path]:
        if not self.api_dir.is_dir():
            return []
        return sorted(
            p for p in self.api_dir.glob("*.json")
            if p.name != PROJECT_FILE and not p.name.startswith(".")
        )

    def load_all(self) -> tuple[list[Collection], list[CollectionLoadWarning]]:
        """Load every collection. Broken files are reported, skipped and never overwritten."""
        collections: list[Collection] = []
        warnings: list[CollectionLoadWarning] = []
        for path in self.collection_files():
            try:
                collections.append(self.load(path))
            except (JsonFileError, ValueError) as exc:
                message = exc.message if isinstance(exc, JsonFileError) else str(exc)
                log.warning("Skipping collection %s: %s", path.name, message)
                warnings.append(CollectionLoadWarning(path.name, message))
        return collections, warnings

    def load(self, path: Path) -> Collection:
        return Collection.from_dict(read_json(path), fallback_id=path.stem)

    def save(self, collection: Collection) -> None:
        write_json_atomic(self.path_for(collection.id), collection.to_dict())

    def delete(self, collection_id: str) -> None:
        self.path_for(collection_id).unlink(missing_ok=True)

    def exists(self, collection_id: str) -> bool:
        return self.path_for(collection_id).exists()
