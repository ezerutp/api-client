import ast
import re
import string
from pathlib import Path

import pytest

from app import i18n
from app.i18n import es, resolve_language, set_language, tr, trn

APP_DIR = Path(__file__).resolve().parent.parent / "app"
# Messages produced by Python's json module; they are looked up dynamically.
DYNAMIC_KEYS = {k for k in es.MESSAGES if k[:1].isupper() and (
    k.startswith(("Expecting", "Unterminated", "Invalid control", "Invalid \\", "Extra data", "Illegal trailing")))}


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "trn"):
                count = 2 if node.func.id == "trn" else 1
                for arg in node.args[:count]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        keys.add(arg.value)
    return keys


def placeholders(text: str) -> set[str]:
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # {{variables}} are literal text, not format fields
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.fixture(autouse=True)
def english_afterwards():
    yield
    set_language("en")


def test_every_used_string_has_a_spanish_translation():
    missing = sorted(used_keys() - set(es.MESSAGES))
    assert not missing, "Missing Spanish translations:\n" + "\n".join(missing)


def test_catalog_has_no_stale_entries():
    stale = sorted(set(es.MESSAGES) - used_keys() - DYNAMIC_KEYS - {"Language", "Interface language.",
                                                                  "System default"})
    assert not stale, "Unused translations:\n" + "\n".join(stale)


def test_placeholders_match():
    for key, value in es.MESSAGES.items():
        assert placeholders(key) == placeholders(value), key


def test_variables_are_kept_verbatim():
    for key, value in es.MESSAGES.items():
        assert re.findall(r"\{\{\w+\}\}", key) == re.findall(r"\{\{\w+\}\}", value), key


def test_translation_and_fallback():
    set_language("es")
    assert tr("Send") == "Enviar"
    assert tr("Could not connect to:\n{origin}", origin="http://x") == "No se pudo conectar con:\nhttp://x"
    assert tr("A string nobody translated") == "A string nobody translated"
    set_language("en")
    assert tr("Send") == "Send"


def test_plurals():
    set_language("es")
    assert trn("{n} request", "{n} requests", 1) == "1 petición"
    assert trn("{n} request", "{n} requests", 3) == "3 peticiones"


def test_language_resolution(monkeypatch):
    assert resolve_language("es") == "es"
    assert resolve_language("fr") == "en"
    monkeypatch.setenv("LANGUAGE", "es_PE:es")
    assert resolve_language("system") == "es"
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "en")
    assert resolve_language("system") == "en"


def test_network_errors_are_translated():
    import httpx

    from app.network.errors import map_exception

    set_language("es")
    error = map_exception(httpx.ConnectError("[Errno 111] Connection refused"), "http://localhost:8080/api", 30)
    assert error.title == "Conexión rechazada"
    assert "http://localhost:8080" in error.message


def test_json_errors_are_translated():
    from app.services.json_service import validate_json

    set_language("es")
    result = validate_json('{\n  "a": 1\n  "b": 2\n}')
    assert result.summary == "JSON inválido — línea 3: Se esperaba el separador ','"
