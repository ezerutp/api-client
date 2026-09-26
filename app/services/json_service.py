"""JSON validation/formatting that tolerates ``{{variables}}`` inside the document.

``{"id": {{product_id}}}`` is not valid JSON until variables are resolved, but
it is what users write. Each variable is swapped for a unique numeric
placeholder (valid both inside and outside strings), then restored.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.i18n import tr
from app.services.variable_service import VARIABLE_PATTERN

_PLACEHOLDER_PREFIX = "91827364"
_PLACEHOLDER_PATTERN = re.compile(_PLACEHOLDER_PREFIX + r"(\d{5})5463728")


@dataclass(frozen=True)
class JsonValidation:
    valid: bool
    message: str = ""
    line: int | None = None
    column: int | None = None

    @property
    def summary(self) -> str:
        if self.valid:
            return tr("Valid JSON")
        if self.line:
            return tr("Invalid JSON — line {line}: {message}", line=self.line, message=translate_json_error(self.message))
        return tr("Invalid JSON: {message}", message=translate_json_error(self.message))


def translate_json_error(message: str) -> str:
    """Python's json module reports errors in English; translate the known ones."""
    head, sep, tail = message.partition(": line")
    return tr(head) + (sep + tail if sep else "")


def _protect(text: str) -> tuple[str, list[str]]:
    originals: list[str] = []

    def replace(match: re.Match[str]) -> str:
        originals.append(match.group(0))
        return f"{_PLACEHOLDER_PREFIX}{len(originals) - 1:05d}5463728"

    return VARIABLE_PATTERN.sub(replace, text), originals


def _restore(text: str, originals: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return originals[index] if index < len(originals) else match.group(0)

    return _PLACEHOLDER_PATTERN.sub(replace, text)


def validate_json(text: str) -> JsonValidation:
    if not text.strip():
        return JsonValidation(valid=True)
    protected, _ = _protect(text)
    try:
        json.loads(protected)
    except json.JSONDecodeError as exc:
        return JsonValidation(valid=False, message=exc.msg, line=exc.lineno, column=exc.colno)
    return JsonValidation(valid=True)


def format_json(text: str, indent: int = 2) -> str:
    """Pretty print. Raises ``json.JSONDecodeError`` if the document is invalid."""
    if not text.strip():
        return text
    protected, originals = _protect(text)
    parsed = json.loads(protected)
    return _restore(json.dumps(parsed, indent=indent, ensure_ascii=False), originals)


def minify_json(text: str) -> str:
    return json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
