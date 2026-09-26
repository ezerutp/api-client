"""Human readable JSON files written atomically."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonFileError(Exception):
    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path.name}: {message}")
        self.path = path
        self.message = message


def read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise JsonFileError(path, "file not found") from None
    except UnicodeDecodeError:
        raise JsonFileError(path, "file is not valid UTF-8 text") from None
    except OSError as exc:
        raise JsonFileError(path, f"cannot read file ({exc.strerror or exc})") from None
    if not text.strip():
        raise JsonFileError(path, "file is empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonFileError(path, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from None


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_json_atomic(path: Path, data: Any) -> None:
    """Write to a temp file in the same folder, then rename: never leaves a half-written file."""
    write_text_atomic(path, dump_json(data))


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
