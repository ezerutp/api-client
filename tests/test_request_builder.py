import base64
import json

import pytest

from app.models.api_request import (
    ApiRequest, BodyType, HttpMethod, PathParameter, RequestBody, RequestHeader, RequestParameter,
)
from app.models.auth import Authentication, AuthType
from app.network.errors import ErrorKind, RequestError
from app.services.curl_service import build_curl
from app.services.request_builder import RequestBuilder, extract_path_param_names
from app.services.variable_service import VariableContext

CTX = VariableContext(
    values={"base_url": "http://localhost:8080", "token": "s3cr3t-token", "product_id": "15"},
    secret_names=frozenset({"token"}),
    environment="local",
)


def build(request: ApiRequest):
    return RequestBuilder(CTX).build(request)


def test_query_params_only_enabled_ones():
    request = ApiRequest(name="x", url="{{base_url}}/api/productos", params=[
        RequestParameter("page", "0"), RequestParameter("size", "20"),
        RequestParameter("sort", "nombre"), RequestParameter("category", "tecnologia", enabled=False),
    ])
    assert build(request).url == "http://localhost:8080/api/productos?page=0&size=20&sort=nombre"


def test_query_params_are_encoded_and_merged_with_existing_query():
    request = ApiRequest(name="x", url="{{base_url}}/api?a=1", params=[RequestParameter("q", "hola mundo")])
    assert build(request).url == "http://localhost:8080/api?a=1&q=hola%20mundo"


def test_path_params_resolved_and_encoded():
    request = ApiRequest(name="x", url="{{base_url}}/api/productos/{id}/{slug}",
                         path_params=[PathParameter("id", "{{product_id}}"), PathParameter("slug", "a b/c")])
    assert build(request).url == "http://localhost:8080/api/productos/15/a%20b%2Fc"


def test_missing_path_param_value_is_an_error():
    request = ApiRequest(name="x", url="{{base_url}}/api/productos/{id}", path_params=[PathParameter("id", "")])
    with pytest.raises(RequestError) as info:
        build(request)
    assert "{id}" in info.value.message


def test_extract_path_param_names_ignores_variables_and_query():
    assert extract_path_param_names("{{base_url}}/api/{id}/items/{itemId}?x={y}") == ["id", "itemId"]


def test_missing_variable_error():
    request = ApiRequest(name="x", url="{{missing_host}}/api")
    with pytest.raises(RequestError) as info:
        build(request)
    assert info.value.kind is ErrorKind.MISSING_VARIABLE
    assert "missing_host" in info.value.message


def test_scheme_is_added_when_missing():
    assert build(ApiRequest(name="x", url="localhost:8080/api")).url == "http://localhost:8080/api"


def test_invalid_scheme_rejected():
    with pytest.raises(RequestError) as info:
        build(ApiRequest(name="x", url="ftp://host/file"))
    assert info.value.kind is ErrorKind.INVALID_URL


def test_bearer_auth_overrides_authorization_header():
    request = ApiRequest(name="x", url="{{base_url}}", headers=[RequestHeader("Authorization", "old")],
                         auth=Authentication(AuthType.BEARER, token="{{token}}"))
    prepared = build(request)
    assert prepared.header("Authorization") == "Bearer s3cr3t-token"
    assert [k for k, _ in prepared.headers].count("Authorization") == 1


def test_basic_auth():
    request = ApiRequest(name="x", url="{{base_url}}", auth=Authentication(AuthType.BASIC, username="u", password="p"))
    expected = "Basic " + base64.b64encode(b"u:p").decode()
    assert build(request).header("Authorization") == expected


def test_unused_auth_fields_do_not_require_variables():
    request = ApiRequest(name="x", url="{{base_url}}", auth=Authentication(AuthType.NONE, token="{{nope}}"))
    assert build(request).header("Authorization") is None


def test_json_body_with_variables_and_content_type():
    request = ApiRequest(name="x", method=HttpMethod.POST, url="{{base_url}}/api",
                         body=RequestBody(BodyType.JSON, '{"id": {{product_id}}}'))
    prepared = build(request)
    assert json.loads(prepared.body) == {"id": 15}
    assert prepared.header("Content-Type") == "application/json"


def test_explicit_content_type_is_respected():
    request = ApiRequest(name="x", method=HttpMethod.POST, url="{{base_url}}",
                         headers=[RequestHeader("content-type", "application/vnd.api+json")],
                         body=RequestBody(BodyType.JSON, "{}"))
    prepared = build(request)
    assert [k.lower() for k, _ in prepared.headers].count("content-type") == 1


def test_invalid_json_body_reports_line():
    request = ApiRequest(name="x", method=HttpMethod.POST, url="{{base_url}}",
                         body=RequestBody(BodyType.JSON, '{\n  "a": 1,\n  "b": \n}'))
    with pytest.raises(RequestError) as info:
        build(request)
    assert info.value.kind is ErrorKind.INVALID_JSON
    assert info.value.line == 4


def test_curl_masks_secrets_by_default():
    request = ApiRequest(name="x", method=HttpMethod.POST, url="{{base_url}}/api/productos",
                         auth=Authentication(AuthType.BEARER, token="{{token}}"),
                         body=RequestBody(BodyType.JSON, '{"nombre":"Monitor"}'))
    prepared = build(request)
    assert prepared.contains_secrets
    masked = build_curl(prepared)
    assert "s3cr3t-token" not in masked
    assert "Authorization: Bearer ****" in masked
    assert "-X POST" in masked and "--data-raw" in masked
    assert "s3cr3t-token" in build_curl(prepared, mask_secrets=False)
