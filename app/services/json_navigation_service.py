"""Maps JSON paths to text positions so the object view and the editor can follow each other.

``json.loads`` throws positions away, so this module has its own small recursive
parser that walks the real JSON grammar (strings with escapes and braces,
nested objects/arrays, arbitrary whitespace, one-line documents) and records,
for every node, where it starts and ends in the text. It never evaluates the
content. Bare ``{{variables}}`` are accepted as values, like everywhere else in
the app.

Paths are tuples (``("carrera", "nombre")``, ``("productos", 1, "id")``), the same
ones the object view keeps, so repeated key names can never be confused.
``format_path`` turns them into the text shown by "Copy path".
"""

from __future__ import annotations

import bisect
import json
import re
from typing import NamedTuple

from app.services.variable_service import VARIABLE_PATTERN

Path = tuple[str | int, ...]

_WHITESPACE = re.compile(r"[ \t\n\r]*")
_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
# Python's json module accepts these too; mirror it so both agree on validity.
_LITERAL = re.compile(r"true|false|null|NaN|Infinity|-Infinity")
_ASTRAL = re.compile("[\U00010000-\U0010ffff]")
_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def format_path(path: Path) -> str:
    """``("carrera", "id")`` -> ``carrera.id``; ``("items", 0, "a b")`` -> ``items[0]["a b"]``."""
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        elif _IDENTIFIER.match(part):
            text += f".{part}" if text else part
        else:
            text += f"[{json.dumps(part, ensure_ascii=False)}]"
    return text


class JsonSyntaxError(ValueError):
    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} (char {position})")
        self.position = position


class JsonLocation(NamedTuple):
    """Character range of one node (Python string indices)."""

    path: Path
    start: int              # member: opening quote of the key; element/root: first char of the value
    end: int                # one past the last char of the value
    value_start: int
    key_end: int | None = None  # one past the closing quote of the key (members only)

    @property
    def is_member(self) -> bool:
        return self.key_end is not None


class JsonDocumentIndex:
    """Result of indexing one text: ``path -> location`` plus the reverse lookup."""

    def __init__(self, text: str, locations: dict[Path, JsonLocation]) -> None:
        self.text = text
        self.locations = locations
        self._children: dict[Path, list[JsonLocation]] = {}
        for location in locations.values():
            if location.path:
                self._children.setdefault(location.path[:-1], []).append(location)
        for children in self._children.values():
            children.sort(key=lambda loc: loc.start)
        self._ordered = sorted(locations.values(), key=lambda loc: loc.start)
        self._starts = [loc.start for loc in self._ordered]
        # QTextDocument counts UTF-16 code units: characters beyond the BMP (emoji) take two.
        self._astral = [m.start() for m in _ASTRAL.finditer(text)]
        self._astral_utf16 = [index + n for n, index in enumerate(self._astral)]

    def location(self, path: Path) -> JsonLocation | None:
        return self.locations.get(tuple(path))

    def path_at(self, offset: int, line_start: int | None = None, line_end: int | None = None) -> Path | None:
        """Deepest node under ``offset``.

        With the bounds of the cursor's line, a cursor sitting in the whitespace or
        after the trailing comma of a member still resolves to that member.
        """
        best = self._deepest_containing(offset)
        if best is None:
            return None
        if line_start is None or line_end is None:
            return best.path
        children = self._children.get(best.path, [])
        starts = [child.start for child in children]
        index = bisect.bisect_right(starts, offset) - 1
        if index >= 0 and line_start <= children[index].start < line_end:
            return children[index].path
        if index + 1 < len(children) and line_start <= children[index + 1].start < line_end:
            return children[index + 1].path
        return best.path

    def _deepest_containing(self, offset: int) -> JsonLocation | None:
        # Nodes are nested or disjoint, so among those starting before ``offset`` the
        # first one (walking backwards) that still spans it is the deepest.
        index = bisect.bisect_right(self._starts, offset) - 1
        while index >= 0:
            location = self._ordered[index]
            if location.end >= offset:
                return location
            index -= 1
        return None

    # -- UTF-16 <-> str index ---------------------------------------------------------

    def to_document_position(self, index: int) -> int:
        return index + bisect.bisect_left(self._astral, index)

    def from_document_position(self, position: int) -> int:
        return position - bisect.bisect_left(self._astral_utf16, position)


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.locations: dict[Path, JsonLocation] = {}

    def parse(self) -> dict[Path, JsonLocation]:
        self._value((), None)
        self._skip_whitespace()
        if self.pos != len(self.text):
            raise JsonSyntaxError("Extra data", self.pos)
        return self.locations

    def _skip_whitespace(self) -> None:
        self.pos = _WHITESPACE.match(self.text, self.pos).end()  # type: ignore[union-attr]

    def _expect(self, char: str) -> None:
        self._skip_whitespace()
        if not self.text.startswith(char, self.pos):
            raise JsonSyntaxError(f"Expecting {char!r}", self.pos)
        self.pos += 1

    def _value(self, path: Path, key_range: tuple[int, int] | None) -> None:
        self._skip_whitespace()
        text, start = self.text, self.pos
        char = text[start:start + 1]
        if char == '"':
            self._string()
        elif char == "{" and not text.startswith("{{", start):
            self._object(path)
        elif char == "[":
            self._array(path)
        elif (number := _NUMBER.match(text, start)) is not None and not text.startswith("-Infinity", start):
            self.pos = number.end()
        elif (literal := _LITERAL.match(text, start)) is not None:
            self.pos = literal.end()
        elif (variable := VARIABLE_PATTERN.match(text, start)) is not None:
            self.pos = variable.end()
        else:
            raise JsonSyntaxError("Expecting value", start)
        self.locations[path] = JsonLocation(
            path=path,
            start=key_range[0] if key_range else start,
            end=self.pos,
            value_start=start,
            key_end=key_range[1] if key_range else None,
        )

    def _string(self) -> str:
        match = _STRING.match(self.text, self.pos)
        if match is None:
            raise JsonSyntaxError("Unterminated string", self.pos)
        self.pos = match.end()
        raw = match.group(0)
        return raw[1:-1] if "\\" not in raw else json.loads(raw)

    def _object(self, path: Path) -> None:
        self.pos += 1  # "{"
        self._skip_whitespace()
        if self.text.startswith("}", self.pos):
            self.pos += 1
            return
        while True:
            self._skip_whitespace()
            if not self.text.startswith('"', self.pos):
                raise JsonSyntaxError("Expecting property name enclosed in double quotes", self.pos)
            key_start = self.pos
            key = self._string()
            key_end = self.pos
            self._expect(":")
            child = (*path, key)
            if child in self.locations:
                self._forget(child)  # repeated key: the last one wins, as in json.loads
            self._value(child, (key_start, key_end))
            self._skip_whitespace()
            if self.text.startswith(",", self.pos):
                self.pos += 1
            elif self.text.startswith("}", self.pos):
                self.pos += 1
                return
            else:
                raise JsonSyntaxError("Expecting ',' delimiter", self.pos)

    def _array(self, path: Path) -> None:
        self.pos += 1  # "["
        self._skip_whitespace()
        if self.text.startswith("]", self.pos):
            self.pos += 1
            return
        index = 0
        while True:
            self._value((*path, index), None)
            index += 1
            self._skip_whitespace()
            if self.text.startswith(",", self.pos):
                self.pos += 1
            elif self.text.startswith("]", self.pos):
                self.pos += 1
                return
            else:
                raise JsonSyntaxError("Expecting ',' delimiter", self.pos)

    def _forget(self, path: Path) -> None:
        size = len(path)
        for existing in [p for p in self.locations if p[:size] == path]:
            del self.locations[existing]


def index_json(text: str) -> JsonDocumentIndex:
    """Raises ``JsonSyntaxError`` if ``text`` is not a JSON document."""
    try:
        return JsonDocumentIndex(text, _Parser(text).parse())
    except RecursionError as exc:
        raise JsonSyntaxError("Document nested too deeply", 0) from exc


#: Up to this size the index is built right after each edit settles (well under 200 ms);
#: bigger documents are indexed on the first navigation request and reused afterwards.
EAGER_INDEX_CHARS = 300_000


class JsonNavigationService:
    """Keeps the index of the latest valid text; lookups reuse it until the text changes."""

    def __init__(self) -> None:
        self._index: JsonDocumentIndex | None = None
        self._text: str | None = None

    @property
    def available(self) -> bool:
        return self._index is not None

    @property
    def index(self) -> JsonDocumentIndex | None:
        return self._index

    def update(self, text: str) -> bool:
        """Re-index ``text`` (no-op if unchanged). Returns whether navigation is available."""
        if text != self._text:
            self._text = text
            try:
                self._index = index_json(text) if text.strip() else None
            except JsonSyntaxError:
                self._index = None
        return self._index is not None

    def locate(self, path: Path) -> JsonLocation | None:
        return self._index.location(path) if self._index else None

    def path_at(self, offset: int, line_start: int | None = None, line_end: int | None = None) -> Path | None:
        return self._index.path_at(offset, line_start, line_end) if self._index else None
