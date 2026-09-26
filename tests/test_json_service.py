import pytest

from app.services.json_service import format_json, validate_json


def test_valid_json():
    assert validate_json('{"a": 1}').valid


def test_invalid_json_line():
    result = validate_json('{\n  "a": 1\n  "b": 2\n}')
    assert not result.valid and result.line == 3


def test_variables_do_not_break_validation_or_formatting():
    text = '{"id": {{product_id}}, "auth": "Bearer {{token}}"}'
    assert validate_json(text).valid
    assert format_json(text) == '{\n  "id": {{product_id}},\n  "auth": "Bearer {{token}}"\n}'


def test_format_invalid_raises():
    with pytest.raises(ValueError):
        format_json("{nope}")


def test_unicode_is_preserved():
    assert format_json('{"nombre":"Cañón"}') == '{\n  "nombre": "Cañón"\n}'
