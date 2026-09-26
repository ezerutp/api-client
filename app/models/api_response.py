from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from http import HTTPStatus

_TEXT_TYPES = ("json", "xml", "html", "text", "javascript", "csv", "yaml", "x-www-form-urlencoded")


@dataclass
class ApiResponse:
    status_code: int
    reason: str
    headers: list[tuple[str, str]]
    body: bytes
    elapsed_ms: float
    url: str
    method: str
    http_version: str = "HTTP/1.1"
    request_headers: list[tuple[str, str]] = field(default_factory=list)
    truncated: bool = False
    received_at: datetime = field(default_factory=datetime.now)

    @property
    def status_text(self) -> str:
        reason = self.reason
        if not reason:
            try:
                reason = HTTPStatus(self.status_code).phrase
            except ValueError:
                reason = ""
        return f"{self.status_code} {reason}".strip()

    @property
    def size_bytes(self) -> int:
        header_bytes = sum(len(k) + len(v) + 4 for k, v in self.headers)
        return len(self.body) + header_bytes

    def header(self, name: str) -> str | None:
        lower = name.lower()
        return next((v for k, v in self.headers if k.lower() == lower), None)

    @property
    def content_type(self) -> str:
        return (self.header("content-type") or "").split(";")[0].strip().lower()

    @property
    def charset(self) -> str:
        for part in (self.header("content-type") or "").split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                return value.strip('"')
        return "utf-8"

    @property
    def is_text(self) -> bool:
        if not self.body:
            return True
        content_type = self.content_type
        if not content_type:
            return b"\x00" not in self.body[:2048]
        return any(t in content_type for t in _TEXT_TYPES)

    @cached_property
    def text(self) -> str:
        try:
            return self.body.decode(self.charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    @cached_property
    def json_value(self) -> object | None:
        if not self.body or not self.is_text:
            return None
        looks_like_json = "json" in self.content_type or self.text.lstrip()[:1] in ("{", "[")
        if not looks_like_json:
            return None
        try:
            return json.loads(self.text)
        except ValueError:
            return None

    @property
    def is_json(self) -> bool:
        return self.json_value is not None

    def pretty_body(self) -> str:
        if self.is_json:
            return json.dumps(self.json_value, indent=2, ensure_ascii=False)
        return self.text

    def raw_text(self) -> str:
        lines = [f"{self.http_version} {self.status_text}"]
        lines += [f"{k}: {v}" for k, v in self.headers]
        return "\n".join(lines) + "\n\n" + self.text
