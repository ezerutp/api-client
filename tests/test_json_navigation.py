"""Structural JSON path <-> text position mapping (no Qt)."""

import json

import pytest

from app.services.json_navigation_service import (
    JsonNavigationService,
    JsonSyntaxError,
    format_path,
    index_json,
)

PERSONA = """{
  "id": "id",
  "nombre": "ezer",
  "edad": "32",
  "carrera": {
    "id": "01",
    "nombre": "ing",
    "ciclo": "01"
  },
  "update": "2021254222"
}"""

PRODUCTOS = """{
  "productos": [
    {
      "id": 1,
      "nombre": "Monitor"
    },
    {
      "id": 2,
      "nombre": "Teclado"
    }
  ]
}"""


def member_text(text, path):
    loc = index_json(text).location(path)
    return text[loc.start:loc.end]


def line_of(text, path):
    loc = index_json(text).location(path)
    start = text.rfind("\n", 0, loc.start) + 1
    end = text.find("\n", loc.start)
    return text[start:end if end != -1 else None].strip()


def test_unique_and_repeated_keys_follow_the_full_path():
    assert member_text(PERSONA, ("nombre",)) == '"nombre": "ezer"'
    assert member_text(PERSONA, ("carrera", "nombre")) == '"nombre": "ing"'
    assert line_of(PERSONA, ("carrera", "id")) == '"id": "01",'
    assert line_of(PERSONA, ("id",)) == '"id": "id",'


def test_objects_start_at_their_key():
    assert line_of(PERSONA, ("carrera",)) == '"carrera": {'
    assert member_text(PERSONA, ("carrera",)).endswith("}")


def test_arrays_of_objects():
    assert member_text(PRODUCTOS, ("productos", 1, "nombre")) == '"nombre": "Teclado"'
    assert member_text(PRODUCTOS, ("productos", 0, "nombre")) == '"nombre": "Monitor"'
    element = index_json(PRODUCTOS).location(("productos", 1))
    assert PRODUCTOS[element.start] == "{" and not element.is_member
    assert json.loads(PRODUCTOS[element.start:element.end]) == {"id": 2, "nombre": "Teclado"}


def test_nested_arrays_and_scalar_types():
    text = '{"m": [[1, 2], [3, [true, null]]], "s": "x", "n": -1.5e3, "b": false, "z": null}'
    idx = index_json(text)
    assert text[idx.location(("m", 1, 1, 0)).start:idx.location(("m", 1, 1, 0)).end] == "true"
    assert text[idx.location(("m", 1, 1, 1)).value_start:idx.location(("m", 1, 1, 1)).end] == "null"
    assert text[idx.location(("m", 0, 1)).start:idx.location(("m", 0, 1)).end] == "2"
    for key, raw in {"s": '"x"', "n": "-1.5e3", "b": "false", "z": "null"}.items():
        loc = idx.location((key,))
        assert text[loc.value_start:loc.end] == raw


def test_strings_with_braces_quotes_and_escapes_do_not_confuse_the_parser():
    text = r'{"a": "} { ] [ \"nombre\": 1", "k\"ey": {"nombre": "b\\"}, "nombre": "real"}'
    assert member_text(text, ("nombre",)) == '"nombre": "real"'
    assert member_text(text, ('k"ey', "nombre")) == r'"nombre": "b\\"'


def test_compact_and_oddly_spaced_documents():
    compact = json.dumps(json.loads(PERSONA), separators=(",", ":"))
    assert member_text(compact, ("carrera", "nombre")) == '"nombre":"ing"'
    spaced = '{\n\t"carrera"  :\r\n {   "nombre"\t:   "ing"   }   }'
    assert member_text(spaced, ("carrera", "nombre")) == '"nombre"\t:   "ing"'


def test_repeated_key_in_same_object_uses_the_last_one_like_json_loads():
    text = '{"a": {"x": 1}, "a": 2}'
    idx = index_json(text)
    assert text[idx.location(("a",)).value_start:idx.location(("a",)).end] == "2"
    assert idx.location(("a", "x")) is None


def test_variables_are_values():
    text = '{"id": {{product_id}}, "t": "Bearer {{token}}"}'
    assert member_text(text, ("id",)) == '"id": {{product_id}}'


@pytest.mark.parametrize("text", ['{"a": 1,}', '{"a" 1}', '[1 2]', '{"a": "x}', "{} x", "", "{'a': 1}"])
def test_invalid_documents_raise(text):
    with pytest.raises(JsonSyntaxError):
        index_json(text)


def test_reverse_lookup():
    idx = index_json(PERSONA)
    inside_ing = PERSONA.index('"ing"') + 2
    assert idx.path_at(inside_ing) == ("carrera", "nombre")
    on_key = PERSONA.index('"ciclo"') + 1
    assert idx.path_at(on_key) == ("carrera", "ciclo")
    # After the trailing comma / in the indentation of a line, the line's member wins.
    line_start = PERSONA.index('    "nombre": "ing"')
    line_end = PERSONA.index("\n", line_start)
    assert idx.path_at(line_end, line_start, line_end) == ("carrera", "nombre")
    assert idx.path_at(line_start, line_start, line_end) == ("carrera", "nombre")
    assert idx.path_at(0) == ()


def test_utf16_positions_account_for_emoji():
    text = '{"e": "😀😀", "n": 1}'
    idx = index_json(text)
    start = idx.location(("n",)).start
    assert idx.to_document_position(start) == start + 2
    assert idx.from_document_position(start + 2) == start


def test_service_reuses_index_until_text_changes_and_disables_on_invalid():
    service = JsonNavigationService()
    assert service.update(PERSONA)
    first = service.index
    assert service.update(PERSONA) and service.index is first
    assert not service.update('{"a": ')
    assert service.locate(("id",)) is None and service.path_at(3) is None
    assert service.update(PRODUCTOS) and service.locate(("productos", 1)) is not None


def test_format_path():
    assert format_path(("carrera", "nombre")) == "carrera.nombre"
    assert format_path(("productos", 1, "nombre")) == "productos[1].nombre"
    assert format_path(("a b", 0)) == '["a b"][0]'
