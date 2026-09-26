import pytest

from app.models.api_request import BodyType, HttpMethod
from app.models.auth import AuthType
from app.services.curl_service import CurlParseError, looks_like_curl, parse_curl

BASE = "https://ide.igp.gob.pe/arcgis/rest/services/monitoreocensis"


def params(request):
    return [(p.key, p.value) for p in request.params]


def headers(request):
    return [(h.key, h.value) for h in request.headers]


def test_simple_get_splits_query_and_uses_base_url():
    result = parse_curl(f"curl '{BASE}/UltimoSismo/MapServer/0/query?where=1%3D1&outFields=*&f=geojson'", BASE)
    request = result.request
    assert request.method is HttpMethod.GET
    assert request.url == "{{base_url}}/UltimoSismo/MapServer/0/query"
    assert params(request) == [("where", "1=1"), ("outFields", "*"), ("f", "geojson")]
    assert request.name == "query"
    assert request.body.type is BodyType.NONE
    assert result.ignored == []


def test_base_url_with_trailing_slash_does_not_double_the_slash():
    request = parse_curl(f"curl {BASE}/UltimoSismo", BASE + "/").request
    assert request.url == "{{base_url}}UltimoSismo"


def test_other_hosts_and_prefix_lookalikes_keep_the_full_url():
    assert parse_curl("curl https://other.com/x", BASE).request.url == "https://other.com/x"
    assert parse_curl(f"curl {BASE}sdsd/x", BASE).request.url == f"{BASE}sdsd/x"


def test_multiline_post_with_json_body_and_bearer_token():
    text = """curl -X POST 'http://localhost:8080/api/productos' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer abc.def' \\
  -H 'X-Trace: 1' \\
  --data-raw '{"nombre":"Monitor","precio":10}'"""
    request = parse_curl(text, "http://localhost:8080").request
    assert request.method is HttpMethod.POST
    assert request.url == "{{base_url}}/api/productos"
    assert headers(request) == [("X-Trace", "1")]
    assert request.auth.type is AuthType.BEARER and request.auth.token == "abc.def"
    assert request.body.type is BodyType.JSON
    assert request.body.content == '{\n  "nombre": "Monitor",\n  "precio": 10\n}'
    assert request.body.content_type == ""


def test_data_without_method_is_a_post_and_json_is_detected():
    request = parse_curl("curl http://x/api -d '{\"a\": 1}'").request
    assert request.method is HttpMethod.POST
    assert request.body.type is BodyType.JSON


def test_form_data_keeps_curl_content_type():
    request = parse_curl("curl http://x/login -d user=ana -d 'pass=1 2'").request
    assert request.body.type is BodyType.TEXT
    assert request.body.content == "user=ana&pass=1 2"
    assert request.body.content_type == "application/x-www-form-urlencoded"


def test_custom_content_type_moves_into_the_body():
    request = parse_curl("curl http://x -H 'content-type: application/vnd.api+json' -d '{\"a\":1}'").request
    assert request.body.type is BodyType.JSON
    assert request.body.content_type == "application/vnd.api+json"
    assert headers(request) == []


def test_get_flag_moves_data_to_the_query():
    request = parse_curl("curl -G http://x/search -d q=monitor --data-urlencode 'tag=a b'").request
    assert request.method is HttpMethod.GET
    assert params(request) == [("q", "monitor"), ("tag", "a b")]
    assert request.body.type is BodyType.NONE


def test_chrome_bash_copy_with_ansi_c_quoting_and_bundled_flags():
    text = (
        "curl 'https://api.example.com/v1/items?page=2' \\\n"
        "  -H 'accept: application/json' \\\n"
        "  -H $'x-note: it\\'s ok' \\\n"
        "  --data-raw $'{\"name\":\"caf\\u00e9\\\\n\"}' \\\n"
        "  --compressed -sSL"
    )
    request = parse_curl(text).request
    assert request.method is HttpMethod.POST
    assert request.url == "https://api.example.com/v1/items"
    assert params(request) == [("page", "2")]
    assert ("x-note", "it's ok") in headers(request)
    assert '"name": "café\\n"' in request.body.content


def test_chrome_cmd_copy():
    text = 'curl ^"https://api.example.com/items^" ^\n  -H ^"accept: */*^" ^\n  --data-raw ^"^{^\\^"a^\\^":1^}^"'
    request = parse_curl(text).request
    assert request.url == "https://api.example.com/items"
    assert headers(request) == [("accept", "*/*")]
    assert request.body.type is BodyType.JSON
    assert request.body.content == '{\n  "a": 1\n}'


def test_basic_auth_from_user_flag_and_header():
    assert parse_curl("curl -u ana:s3cr3t http://x").request.auth.username == "ana"
    request = parse_curl("curl http://x -H 'Authorization: Basic YW5hOnMzY3IzdA=='").request
    assert (request.auth.type, request.auth.username, request.auth.password) == (AuthType.BASIC, "ana", "s3cr3t")
    assert headers(request) == []


def test_other_authorization_schemes_stay_as_headers():
    request = parse_curl("curl http://x -H 'Authorization: ApiKey 123'").request
    assert request.auth.type is AuthType.NONE
    assert headers(request) == [("Authorization", "ApiKey 123")]


def test_method_head_long_options_and_shortcuts():
    assert parse_curl("curl -I http://x").request.method is HttpMethod.HEAD
    assert parse_curl("curl -XDELETE http://x/1").request.method is HttpMethod.DELETE
    assert parse_curl("curl --request=PUT --url http://x/1").request.method is HttpMethod.PUT
    request = parse_curl("curl http://x -A 'bot/1' -e http://ref -b 'sid=1'").request
    assert headers(request) == [("User-Agent", "bot/1"), ("Referer", "http://ref"), ("Cookie", "sid=1")]


def test_json_option_sets_json_headers():
    request = parse_curl("curl --json '{\"a\":1}' http://x").request
    assert request.method is HttpMethod.POST
    assert request.body.type is BodyType.JSON
    assert headers(request) == [("Accept", "application/json")]


def test_unsupported_options_are_reported():
    result = parse_curl("curl -F file=@a.png -o out.json -d @body.json http://x/upload")
    assert result.ignored == ["-F file=@a.png", "-d @body.json"]


def test_prompt_prefix_and_detection():
    assert looks_like_curl("$ curl http://x")
    assert looks_like_curl("  CURL http://x")
    assert not looks_like_curl("http://x/curl")
    assert parse_curl("$ curl http://x/a").request.url == "http://x/a"


def test_errors():
    with pytest.raises(CurlParseError):
        parse_curl("wget http://x")
    with pytest.raises(CurlParseError):
        parse_curl("curl -s -H 'a: b'")
    with pytest.raises(CurlParseError):
        parse_curl("curl 'http://x")
