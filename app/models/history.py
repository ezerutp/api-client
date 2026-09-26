from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HistoryEntry:
    timestamp: str
    method: str
    url: str
    status_code: int | None
    elapsed_ms: float | None
    size_bytes: int | None = None
    error: str = ""
    project_path: str = ""
    request_id: str = ""
    request_name: str = ""
    id: int | None = None

    @property
    def succeeded(self) -> bool:
        return self.status_code is not None
