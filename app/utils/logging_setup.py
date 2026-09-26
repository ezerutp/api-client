"""Logging with secret redaction.

Every record passes through ``RedactingFilter``: known secret values are
replaced by ``****`` and credentials in common shapes (Authorization headers,
``password=...``) are masked even if they were never registered.
"""

from __future__ import annotations

import logging
import re
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

MASK = "****"
_MIN_SECRET_LENGTH = 3

_PATTERNS = [
    re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)(bearer|basic)?\s*[^\s'\",]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)((?:password|passwd|secret|api[_-]?key|token)['\"]?\s*[:=]\s*['\"]?)[^\s'\",&]+"),
]


class SecretRegistry:
    """Thread-safe set of values that must never appear in logs."""

    def __init__(self) -> None:
        self._values: set[str] = set()
        self._lock = threading.Lock()

    def replace_all(self, values: set[str]) -> None:
        with self._lock:
            self._values = {v for v in values if len(v) >= _MIN_SECRET_LENGTH}

    def add(self, value: str) -> None:
        if len(value) >= _MIN_SECRET_LENGTH:
            with self._lock:
                self._values.add(value)

    def redact(self, text: str) -> str:
        with self._lock:
            values = sorted(self._values, key=len, reverse=True)
        for value in values:
            text = text.replace(value, MASK)
        for pattern in _PATTERNS:
            text = pattern.sub(lambda m: f"{m.group(1)}{MASK}", text)
        return text


secret_registry = SecretRegistry()


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = secret_registry.redact(message)
        record.args = None
        return True


def configure_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "api-client.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [handler, console]
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
