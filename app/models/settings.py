from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass
class NetworkSettings:
    timeout_seconds: float = 30.0
    verify_ssl: bool = True
    follow_redirects: bool = True
    #: Reserved for future use (proxy / client certificates).
    proxy: str = ""


@dataclass
class AppSettings:
    open_last_project: bool = True
    autosave: bool = True
    autosave_delay_ms: int = 700
    recent_limit: int = 10
    history_limit: int = 500
    theme: str = "dark"  # dark | light | system
    editor_font_size: int = 13
    network: NetworkSettings = field(default_factory=NetworkSettings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppSettings:
        defaults = cls()
        values: dict[str, Any] = {}
        for f in fields(cls):
            if f.name == "network" or f.name not in raw:
                continue
            default = getattr(defaults, f.name)
            value = raw[f.name]
            if isinstance(default, bool):
                values[f.name] = value if isinstance(value, bool) else default
            elif isinstance(value, type(default)) or (isinstance(default, float) and isinstance(value, int)):
                values[f.name] = value
        network_raw = raw.get("network") if isinstance(raw.get("network"), dict) else {}
        network_defaults = NetworkSettings()
        network_values: dict[str, Any] = {}
        for f in fields(NetworkSettings):
            if f.name in network_raw:
                default = getattr(network_defaults, f.name)
                value = network_raw[f.name]
                if isinstance(default, bool):
                    if isinstance(value, bool):
                        network_values[f.name] = value
                elif isinstance(default, float) and isinstance(value, (int, float)) and not isinstance(value, bool):
                    network_values[f.name] = float(value)
                elif isinstance(value, type(default)):
                    network_values[f.name] = value
        return cls(**values, network=NetworkSettings(**network_values))
