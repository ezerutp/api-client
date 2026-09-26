from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models._common import as_dict, as_list, as_str
from app.models.environment import Environment

SCHEMA_VERSION = 1


@dataclass
class Project:
    """Content of ``api-client/project.json``."""

    name: str
    base_url: str = "http://localhost:8080"
    #: Default environment for people opening the project for the first time.
    #: The environment each user picks is remembered locally, not here.
    active_environment: str = "local"
    variables: dict[str, str] = field(default_factory=dict)
    environments: dict[str, Environment] = field(default_factory=dict)
    #: Display order of collections (by id). Unlisted collections go last.
    collection_order: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def new(cls, name: str, base_url: str) -> Project:
        return cls(
            name=name,
            base_url=base_url,
            active_environment="local",
            environments={"local": Environment("local", {"base_url": base_url})},
        )

    def environment(self, name: str | None) -> Environment | None:
        if name is None:
            return None
        return self.environments.get(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "base_url": self.base_url,
            "active_environment": self.active_environment,
            "variables": dict(self.variables),
            "environments": {name: env.to_dict() for name, env in self.environments.items()},
            "collections": list(self.collection_order),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Project:
        data = as_dict(raw)
        if not data:
            raise ValueError("project.json must contain a JSON object")
        environments = {
            str(name): Environment.from_dict(str(name), env)
            for name, env in as_dict(data.get("environments")).items()
        }
        version = data.get("schema_version", SCHEMA_VERSION)
        return cls(
            name=as_str(data.get("name")) or "Untitled project",
            base_url=as_str(data.get("base_url")),
            active_environment=as_str(data.get("active_environment")) or next(iter(environments), "local"),
            variables={str(k): as_str(v) for k, v in as_dict(data.get("variables")).items()},
            environments=environments,
            collection_order=[as_str(c) for c in as_list(data.get("collections")) if c],
            schema_version=version if isinstance(version, int) else SCHEMA_VERSION,
        )
