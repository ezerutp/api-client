"""The request model: what gets stored in a collection file."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from app.models._common import as_bool, as_dict, as_list, as_str, new_id, utc_now_iso
from app.models.auth import Authentication


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

    @property
    def usually_has_body(self) -> bool:
        return self in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH)

    @classmethod
    def parse(cls, value: Any) -> HttpMethod:
        try:
            return cls(as_str(value, "GET").upper())
        except ValueError:
            return cls.GET


@dataclass
class KeyValue:
    """A single enabled/key/value row (headers, query params, path params)."""

    key: str = ""
    value: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "key": self.key, "value": self.value}

    @classmethod
    def from_dict(cls, raw: Any) -> Self:
        data = as_dict(raw)
        return cls(
            key=as_str(data.get("key")),
            value=as_str(data.get("value")),
            enabled=as_bool(data.get("enabled"), True),
        )

    @property
    def is_blank(self) -> bool:
        return not self.key.strip() and not self.value.strip()


class RequestHeader(KeyValue):
    """HTTP header row."""


class RequestParameter(KeyValue):
    """Query string parameter row."""


class PathParameter(KeyValue):
    """Value for a ``{name}`` placeholder in the URL path."""


class BodyType(StrEnum):
    NONE = "none"
    JSON = "json"
    TEXT = "text"

    @property
    def label(self) -> str:
        return {"none": "None", "json": "JSON", "text": "Text"}[self.value]

    @property
    def default_content_type(self) -> str | None:
        return {"none": None, "json": "application/json", "text": "text/plain"}[self.value]


@dataclass
class RequestBody:
    type: BodyType = BodyType.NONE
    content: str = ""
    #: Overrides the default Content-Type of the body type when set.
    content_type: str = ""

    @property
    def effective_content_type(self) -> str | None:
        return self.content_type or self.type.default_content_type

    def to_dict(self) -> dict[str, Any] | None:
        if self.type is BodyType.NONE and not self.content:
            return None
        data: dict[str, Any] = {"type": self.type.value, "content": self.content}
        if self.content_type:
            data["content_type"] = self.content_type
        return data

    @classmethod
    def from_dict(cls, raw: Any) -> RequestBody:
        if raw is None:
            return cls()
        if isinstance(raw, str):  # tolerate hand written "body": "..."
            return cls(type=BodyType.TEXT, content=raw)
        data = as_dict(raw)
        try:
            body_type = BodyType(as_str(data.get("type"), "none").lower())
        except ValueError:
            body_type = BodyType.TEXT
        content = data.get("content")
        if not isinstance(content, str) and content is not None:
            # Someone stored a JSON object directly; keep it as formatted text.
            import json

            content = json.dumps(content, indent=2, ensure_ascii=False)
        return cls(type=body_type, content=content or "", content_type=as_str(data.get("content_type")))


@dataclass
class ApiRequest:
    name: str
    method: HttpMethod = HttpMethod.GET
    url: str = ""
    params: list[RequestParameter] = field(default_factory=list)
    path_params: list[PathParameter] = field(default_factory=list)
    headers: list[RequestHeader] = field(default_factory=list)
    auth: Authentication = field(default_factory=Authentication)
    body: RequestBody = field(default_factory=RequestBody)
    description: str = ""
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "method": self.method.value,
            "url": self.url,
        }
        if self.description:
            data["description"] = self.description
        data["params"] = [p.to_dict() for p in self.params if not p.is_blank]
        data["path_params"] = [p.to_dict() for p in self.path_params if p.key]
        data["headers"] = [h.to_dict() for h in self.headers if not h.is_blank]
        data["auth"] = self.auth.to_dict()
        data["body"] = self.body.to_dict()
        data["created_at"] = self.created_at
        data["updated_at"] = self.updated_at
        return data

    @classmethod
    def from_dict(cls, raw: Any) -> ApiRequest:
        data = as_dict(raw)
        if not data:
            raise ValueError("request entry must be a JSON object")
        now = utc_now_iso()
        return cls(
            id=as_str(data.get("id")) or new_id(),
            name=as_str(data.get("name")) or "Untitled request",
            method=HttpMethod.parse(data.get("method")),
            url=as_str(data.get("url")),
            description=as_str(data.get("description")),
            params=[RequestParameter.from_dict(p) for p in as_list(data.get("params"))],
            path_params=[PathParameter.from_dict(p) for p in as_list(data.get("path_params"))],
            headers=[RequestHeader.from_dict(h) for h in as_list(data.get("headers"))],
            auth=Authentication.from_dict(data.get("auth")),
            body=RequestBody.from_dict(data.get("body")),
            created_at=as_str(data.get("created_at")) or now,
            updated_at=as_str(data.get("updated_at")) or now,
        )

    def clone(self, *, name: str | None = None, keep_id: bool = False) -> ApiRequest:
        copy = ApiRequest.from_dict(self.to_dict())
        copy.auth = self.auth.copy()
        if not keep_id:
            copy.id = new_id()
            copy.created_at = copy.updated_at = utc_now_iso()
        if name is not None:
            copy.name = name
        return copy
