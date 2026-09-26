from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models._common import as_dict, as_str


@dataclass
class Environment:
    """A named set of variables such as ``local`` or ``production``.

    Secret values are not stored here but in ``.secrets.json``.
    """

    name: str
    variables: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, str]:
        return dict(self.variables)

    @classmethod
    def from_dict(cls, name: str, raw: Any) -> Environment:
        data = as_dict(raw)
        # Accept both {"base_url": ...} and {"variables": {...}} layouts.
        if set(data) == {"variables"} and isinstance(data["variables"], dict):
            data = data["variables"]
        return cls(name=name, variables={str(k): as_str(v) for k, v in data.items()})

    @property
    def display_name(self) -> str:
        return self.name[:1].upper() + self.name[1:]
