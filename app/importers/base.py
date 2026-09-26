"""Extension point for importing and exporting collections.

Planned implementations: Spring Boot controllers (``@RestController``,
``@RequestMapping``, ``@GetMapping``...), Postman collections and OpenAPI
documents. Each one only has to turn its source into ``Collection`` objects;
``ProjectService`` takes care of storing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.models.collection import Collection


@dataclass
class ImportResult:
    collections: list[Collection]
    warnings: list[str] = field(default_factory=list)


class CollectionImporter(Protocol):
    #: Shown in menus, e.g. "Spring Boot project" or "Postman collection v2.1".
    label: str

    def can_import(self, source: Path) -> bool: ...

    def import_collections(self, source: Path) -> ImportResult: ...


class CollectionExporter(Protocol):
    label: str
    file_extension: str

    def export(self, collections: list[Collection], destination: Path) -> None: ...


_importers: list[CollectionImporter] = []
_exporters: list[CollectionExporter] = []


def register_importer(importer: CollectionImporter) -> None:
    _importers.append(importer)


def register_exporter(exporter: CollectionExporter) -> None:
    _exporters.append(exporter)


def importers() -> list[CollectionImporter]:
    return list(_importers)


def exporters() -> list[CollectionExporter]:
    return list(_exporters)
