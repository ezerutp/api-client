"""Tiny translation layer (pure Python, usable from services and UI alike).

Source strings are written in English and double as lookup keys::

    tr("Send")                                  -> "Enviar"
    tr("Could not connect to:\\n{origin}", origin=url)
    trn("{n} request", "{n} requests", count)   -> "3 requests" / "3 solicitudes"

Missing translations fall back to English, so a forgotten entry never breaks the UI.
"""

from __future__ import annotations

import locale
import os
from collections.abc import Mapping

from app.i18n import es

SUPPORTED_LANGUAGES: dict[str, str] = {"en": "English", "es": "Español"}
_CATALOGS: dict[str, Mapping[str, str]] = {"es": es.MESSAGES}

_language = "en"


def detect_system_language() -> str:
    candidates = [os.environ.get(name, "") for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")]
    try:
        candidates.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    for value in candidates:
        code = value.split(":")[0].split("_")[0].split(".")[0].lower()
        if code in SUPPORTED_LANGUAGES:
            return code
    return "en"


def resolve_language(preference: str) -> str:
    """``"system"`` -> detected language; unknown codes -> English."""
    if preference == "system":
        return detect_system_language()
    return preference if preference in SUPPORTED_LANGUAGES else "en"


def set_language(preference: str) -> str:
    global _language
    _language = resolve_language(preference)
    return _language


def current_language() -> str:
    return _language


def tr(text: str, /, **values: object) -> str:
    translated = _CATALOGS.get(_language, {}).get(text, text)
    return translated.format(**values) if values else translated


def trn(singular: str, plural: str, n: int, /, **values: object) -> str:
    return tr(singular if n == 1 else plural, n=n, **values)
