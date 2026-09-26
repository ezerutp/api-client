"""Authentication settings attached to a request.

New auth kinds (OAuth2, API key...) are added by extending ``AuthType`` and
registering a strategy in ``app.services.auth_strategies``. Unknown fields are
kept in ``extra`` so files written by newer versions survive a round trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.models._common import as_dict, as_str


class AuthType(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"

    @property
    def label(self) -> str:
        return {"none": "No Auth", "bearer": "Bearer Token", "basic": "Basic Auth"}[self.value]


_KNOWN_KEYS = {"type", "token", "username", "password"}


@dataclass
class Authentication:
    type: AuthType = AuthType.NONE
    token: str = ""
    username: str = ""
    password: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type.value}
        if self.type is AuthType.BEARER:
            data["token"] = self.token
        elif self.type is AuthType.BASIC:
            data["username"] = self.username
            data["password"] = self.password
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, raw: Any) -> Authentication:
        data = as_dict(raw)
        try:
            auth_type = AuthType(as_str(data.get("type"), "none").lower())
        except ValueError:
            auth_type = AuthType.NONE
        return cls(
            type=auth_type,
            token=as_str(data.get("token")),
            username=as_str(data.get("username")),
            password=as_str(data.get("password")),
            extra={k: v for k, v in data.items() if k not in _KNOWN_KEYS},
        )

    def copy(self) -> Authentication:
        return Authentication(self.type, self.token, self.username, self.password, dict(self.extra))
