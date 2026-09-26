from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models._common import as_dict, as_list, as_str
from app.models.api_request import ApiRequest


@dataclass
class Collection:
    """A group of requests, stored as ``api-client/<id>.json``.

    ``base_path`` mirrors a Spring ``@RequestMapping`` and pre-fills the URL of
    new requests created in the collection.
    """

    id: str
    name: str
    base_path: str = ""
    description: str = ""
    requests: list[ApiRequest] = field(default_factory=list)

    @property
    def file_name(self) -> str:
        return f"{self.id}.json"

    def find_request(self, request_id: str) -> ApiRequest | None:
        return next((r for r in self.requests if r.id == request_id), None)

    def index_of(self, request_id: str) -> int:
        for index, request in enumerate(self.requests):
            if request.id == request_id:
                return index
        return -1

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "name": self.name}
        if self.base_path:
            data["base_path"] = self.base_path
        if self.description:
            data["description"] = self.description
        data["requests"] = [r.to_dict() for r in self.requests]
        return data

    @classmethod
    def from_dict(cls, raw: Any, *, fallback_id: str) -> Collection:
        data = as_dict(raw)
        if not data:
            raise ValueError("the file must contain a JSON object")
        requests_raw = data.get("requests", [])
        if not isinstance(requests_raw, list):
            raise ValueError('"requests" must be a list')
        return cls(
            # The file name is the source of truth for the id.
            id=fallback_id,
            name=as_str(data.get("name")) or fallback_id.replace("-", " ").title(),
            base_path=as_str(data.get("base_path")),
            description=as_str(data.get("description")),
            requests=[ApiRequest.from_dict(r) for r in as_list(requests_raw)],
        )
