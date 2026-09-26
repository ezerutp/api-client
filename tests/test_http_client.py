"""Runs real requests against a local stdlib HTTP server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.models.api_request import ApiRequest, BodyType, HttpMethod, RequestBody
from app.models.settings import NetworkSettings
from app.network.errors import ErrorKind, RequestError
from app.services.http_client_service import HttpClientService
from app.services.variable_service import VariableContext


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
        body = json.dumps({"id": 15, **payload}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_post_json(server):
    service = HttpClientService(lambda: NetworkSettings(timeout_seconds=5))
    request = ApiRequest(name="x", method=HttpMethod.POST, url="{{base_url}}/api/productos",
                         body=RequestBody(BodyType.JSON, '{"nombre": "Monitor"}'))
    prepared = service.prepare(request, VariableContext(values={"base_url": server}))
    response = service.execute(prepared)
    assert response.status_code == 201
    assert response.status_text == "201 Created"
    assert response.json_value == {"id": 15, "nombre": "Monitor"}
    assert '"id": 15' in response.pretty_body()
    assert response.elapsed_ms > 0 and response.size_bytes > 0


def test_connection_refused():
    service = HttpClientService(lambda: NetworkSettings(timeout_seconds=5))
    request = ApiRequest(name="x", url="http://127.0.0.1:1/api")
    prepared = service.prepare(request, VariableContext())
    with pytest.raises(RequestError) as info:
        service.execute(prepared)
    assert info.value.kind is ErrorKind.CONNECTION_REFUSED
    assert "127.0.0.1:1" in info.value.message
