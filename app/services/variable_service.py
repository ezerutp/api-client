"""Safe ``{{variable}}`` substitution.

Pure string processing with a regular expression and a dictionary lookup:
nothing is ever evaluated. Variables may reference other variables
(``api_url = {{base_url}}/api``); cycles are detected.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.i18n import tr
from app.models.project import Project
from app.repositories.secrets_repository import Secrets

VARIABLE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.\-]*)\s*\}\}")
_MAX_DEPTH = 10


class VariableError(Exception):
    pass


class MissingVariablesError(VariableError):
    def __init__(self, names: Iterable[str], environment: str | None = None) -> None:
        self.names = sorted(set(names))
        self.environment = environment
        joined = ", ".join("{{" + n + "}}" for n in self.names)
        many = len(self.names) != 1
        if environment:
            template = tr("Variables not defined in environment \"{env}\": {names}") if many else \
                tr("Variable not defined in environment \"{env}\": {names}")
        else:
            template = tr("Variables not defined: {names}") if many else tr("Variable not defined: {names}")
        super().__init__(template.format(env=environment, names=joined))


class CircularVariableError(VariableError):
    def __init__(self, chain: list[str]) -> None:
        self.chain = chain
        super().__init__(tr("Circular variable reference: {chain}", chain=" → ".join(chain)))


@dataclass(frozen=True)
class VariableContext:
    values: Mapping[str, str] = field(default_factory=dict)
    secret_names: frozenset[str] = frozenset()
    environment: str | None = None

    def is_defined(self, name: str) -> bool:
        return name in self.values

    def is_secret(self, name: str) -> bool:
        return name in self.secret_names

    def secret_values(self) -> frozenset[str]:
        resolver = VariableResolver(self)
        values: set[str] = set()
        for name in self.secret_names:
            try:
                values.add(resolver.resolve_variable(name))
            except VariableError:
                values.add(self.values.get(name, ""))
        return frozenset(v for v in values if v)


def find_variables(text: str) -> list[str]:
    """Variable names referenced in ``text``, in order of appearance, without duplicates."""
    return list(dict.fromkeys(m.group(1) for m in VARIABLE_PATTERN.finditer(text or "")))


class VariableResolver:
    def __init__(self, context: VariableContext) -> None:
        self.context = context

    def resolve(self, text: str) -> str:
        if not text or "{{" not in text:
            return text
        missing = self.missing_in([text])
        if missing:
            raise MissingVariablesError(missing, self.context.environment)
        return self._substitute(text, [])

    def resolve_variable(self, name: str) -> str:
        if name not in self.context.values:
            raise MissingVariablesError([name], self.context.environment)
        return self._resolve_name(name, [])

    def missing_in(self, texts: Iterable[str]) -> list[str]:
        """All undefined variables referenced (directly or indirectly) by ``texts``."""
        missing: set[str] = set()
        seen: set[str] = set()
        pending = [name for text in texts for name in find_variables(text)]
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            if name not in self.context.values:
                missing.add(name)
            else:
                pending.extend(find_variables(self.context.values[name]))
        return sorted(missing)

    def _substitute(self, text: str, chain: list[str]) -> str:
        return VARIABLE_PATTERN.sub(lambda m: self._resolve_name(m.group(1), chain), text)

    def _resolve_name(self, name: str, chain: list[str]) -> str:
        if name in chain:
            raise CircularVariableError([*chain, name])
        if len(chain) >= _MAX_DEPTH:
            raise CircularVariableError([*chain, name])
        value = self.context.values.get(name)
        if value is None:
            raise MissingVariablesError([name], self.context.environment)
        return self._substitute(value, [*chain, name]) if "{{" in value else value


def build_variable_context(project: Project, secrets: Secrets, environment: str | None) -> VariableContext:
    """Merge variable sources. Later sources win:

    project base_url < global variables < global secrets < environment variables < environment secrets
    """
    values: dict[str, str] = {}
    if project.base_url:
        values["base_url"] = project.base_url
    values.update(project.variables)
    values.update(secrets.globals)
    env = project.environment(environment)
    if env is not None:
        values.update(env.variables)
    env_secrets = secrets.for_environment(environment)
    values.update(env_secrets)
    secret_names = frozenset(secrets.globals) | frozenset(env_secrets)
    return VariableContext(values=values, secret_names=secret_names, environment=environment)


# -- saving values as variables -------------------------------------------------------

_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*")
_SECRET_HINT = re.compile(r"token|secret|passw|pwd|api[_\-.]?key|auth|session|cookie|credential", re.IGNORECASE)


def is_valid_variable_name(name: str) -> bool:
    return bool(_NAME_PATTERN.fullmatch(name))


def suggest_variable_name(path: Iterable[str | int]) -> str:
    """``("data", "access_token")`` -> ``access_token``; array indexes are skipped."""
    for key in reversed(list(path)):
        if isinstance(key, str):
            name = re.sub(r"[^A-Za-z0-9_.\-]+", "_", key).strip("_.-")
            if name:
                return name if is_valid_variable_name(name) else f"_{name}"
    return "value"


def looks_secret(name: str) -> bool:
    return bool(_SECRET_HINT.search(name))


def variable_text(value: object) -> str:
    """How a JSON value is stored in a variable: strings as-is, everything else as JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
