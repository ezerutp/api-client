"""The command line, driven through ``app.cli.main`` against temporary projects."""

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.cli import is_cli_invocation, main
from app.repositories.secrets_repository import SecretsRepository
from app.services.project_service import ProjectService


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v3/api-docs":
            self._reply(200, {"openapi": "3.0.1", "info": {"title": "Tienda", "version": "v1"}, "paths": {
                "/api/productos": {"get": {"tags": ["producto-controller"], "summary": "Listar productos"}},
                "/api/usuarios": {"get": {"tags": ["usuario-controller"], "summary": "Listar usuarios"}},
            }})
        elif self.path == "/missing":
            self._reply(404, {"error": "not found"})
        else:
            self._reply(200, {"path": self.path, "auth": self.headers.get("Authorization")})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self._reply(201, {"id": 1, **json.loads(self.rfile.read(length))})


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("API_CLIENT_DATA_DIR", str(tmp_path / "data"))


class Run:
    def __init__(self, root):
        self.root = root

    def __call__(self, *args: str, stdin: str = "", expect: int = 0) -> str:
        out, err = io.StringIO(), io.StringIO()
        code = main([*args, "-C", str(self.root)] if args and args[0] != "--version" else list(args),
                     out=out, err=err, stdin=io.StringIO(stdin))
        self.err = err.getvalue()
        assert code == expect, self.err
        return out.getvalue()


@pytest.fixture
def cli(tmp_path):
    root = tmp_path / "backend"
    root.mkdir()
    run = Run(root)
    run("project", "init", str(root), "--name", "Tienda", "--base-url", "http://localhost:8080")
    return run


def service(run: Run) -> ProjectService:
    return ProjectService.open(run.root / "api-client").service


def test_dispatch_keeps_the_desktop_app_for_folders():
    assert not is_cli_invocation([])
    assert not is_cli_invocation(["~/backend-tienda"])
    assert is_cli_invocation(["request", "ls"])
    assert is_cli_invocation(["--help"])


def test_project_init_show_and_set(cli):
    shown = json.loads(cli("project", "show", "--json"))
    assert shown["name"] == "Tienda" and shown["environments"] == ["local"]
    cli("project", "set", "--name", "Shop", "--base-url", "http://localhost:9090")
    assert service(cli).project.name == "Shop"
    assert service(cli).project.environments["local"].variables["base_url"] == "http://localhost:9090"
    cli("project", "init", str(cli.root), expect=1)
    assert "already has" in cli.err


def test_project_is_found_from_a_subfolder(cli):
    nested = cli.root / "src" / "main"
    nested.mkdir(parents=True)
    out = io.StringIO()
    assert main(["collection", "ls", "-C", str(nested)], out=out, err=io.StringIO()) == 0


def test_collection_lifecycle(cli):
    cli("collection", "add", "Productos", "--base-path", "api/productos")
    cli("col", "add", "Usuarios")
    assert [c["id"] for c in json.loads(cli("collection", "ls", "--json"))] == ["productos", "usuarios"]
    cli("collection", "rename", "Productos", "Products")
    cli("collection", "duplicate", "products")
    cli("collection", "move", "usuarios", "up", "2")
    assert [c.id for c in service(cli).collections] == ["usuarios", "products", "products-copy"]
    assert service(cli).collection("products").base_path == "/api/productos"
    cli("collection", "rm", "products-copy", expect=1)  # not interactive and no --yes
    cli("collection", "rm", "products-copy", "--yes")
    assert [c.id for c in service(cli).collections] == ["usuarios", "products"]
    cli("collection", "rm", "nope", "-y", expect=1)
    assert "Unknown collection" in cli.err


def test_request_add_edit_and_selectors(cli):
    cli("collection", "add", "Productos", "--base-path", "/api/productos")
    cli("request", "add", "productos", "Crear", "-X", "post", "-H", "Accept: application/json",
        "--bearer", "{{token}}", "-d", '{"nombre": "Monitor"}', "-q", "page=1")
    cli("request", "add", "Productos", "Ver", "--url", "{{base_url}}/api/productos/{id}", "-P", "id=7")
    _, crear = service(cli).all_requests()[0]
    assert crear.method.value == "POST" and crear.url == "{{base_url}}/api/productos"
    assert crear.auth.token == "{{token}}" and crear.body.content == '{"nombre": "Monitor"}'
    assert [(h.key, h.value) for h in crear.headers] == [("Accept", "application/json")]

    cli("request", "edit", "productos/crear", "-H", "accept: text/plain", "--remove-query", "page",
        "--basic", "ana:secreto", "--name", "Crear producto")
    shown = json.loads(cli("request", "show", crear.id))
    assert shown["name"] == "Crear producto" and shown["params"] == []
    assert shown["headers"] == [{"enabled": True, "key": "accept", "value": "text/plain"}]
    assert shown["auth"] == {"type": "basic", "username": "ana", "password": "secreto"}

    cli("request", "edit", "Crear producto", "-d", "{bad")
    assert "not valid" in cli.err
    assert [r["name"] for r in json.loads(cli("request", "ls", "productos", "--json"))] == ["Crear producto", "Ver"]


def test_request_body_from_file_and_stdin(cli, tmp_path):
    cli("collection", "add", "Productos")
    body = tmp_path / "body.json"
    body.write_text('{"a": 1}')
    cli("request", "add", "productos", "Desde archivo", "-X", "POST", "-d", f"@{body}")
    cli("request", "add", "productos", "Desde stdin", "-X", "PUT", "-d", "-", stdin='{"b": 2}')
    contents = [r.body.content for _, r in service(cli).all_requests()]
    assert contents == ['{"a": 1}', '{"b": 2}']


def test_request_rename_duplicate_move_delete(cli):
    cli("collection", "add", "A")
    cli("collection", "add", "B")
    cli("request", "add", "a", "Listar")
    cli("request", "duplicate", "Listar")
    cli("request", "rename", "Listar copy", "Listar todo")
    cli("request", "move", "Listar todo", "b")
    cli("request", "move", "a/listar", "b", "--index", "1")
    assert [r.name for r in service(cli).collection("b").requests] == ["Listar", "Listar todo"]
    cli("request", "rm", "Listar", "-y")
    assert [name for name in (r.name for _, r in service(cli).all_requests())] == ["Listar todo"]


def test_ambiguous_request_names_ask_for_the_collection(cli):
    cli("collection", "add", "A")
    cli("collection", "add", "B")
    cli("request", "add", "a", "Listar")
    cli("request", "add", "b", "Listar")
    cli("request", "show", "Listar", expect=1)
    assert "More than one request" in cli.err
    assert json.loads(cli("request", "show", "b/Listar"))["collection"] == "b"


def test_environments_and_variables(cli):
    cli("env", "add", "Dev", "--base-url", "http://dev")
    cli("var", "set", "token", "abc", "--secret", "-e", "dev")
    cli("var", "set", "tenant", "-", stdin="acme\n")
    cli("env", "use", "dev")
    cli("env", "duplicate", "dev", "qa")
    cli("env", "rename", "dev", "staging")
    project = service(cli)
    assert project.environment_names == ["local", "staging", "qa"]
    assert project.project.active_environment == "staging"
    assert project.secrets.by_environment == {"qa": {"token": "abc"}, "staging": {"token": "abc"}}
    assert project.project.variables == {"tenant": "acme"}

    listed = json.loads(cli("var", "ls", "-e", "staging", "--json"))
    assert {"scope": "staging", "name": "token", "value": "••••••", "secret": True} in listed
    assert "abc" in cli("var", "ls", "--show-secrets")

    cli("var", "rm", "token", "-e", "staging")
    cli("var", "rm", "token", "-e", "staging", expect=1)
    cli("env", "rm", "qa", "-y")
    assert SecretsRepository(cli.root / "api-client").load()[0].by_environment == {}
    cli("var", "set", "1bad", "x", expect=1)


def test_run_curl_and_history(cli, server):
    cli("var", "set", "base_url", server, "-e", "local")
    cli("var", "set", "token", "s3cret", "--secret")
    cli("collection", "add", "Productos", "--base-path", "/api/productos")
    cli("request", "add", "productos", "Listar", "--bearer", "{{token}}")
    cli("request", "add", "productos", "Crear", "-X", "POST", "-d", '{"nombre": "Monitor"}')
    cli("request", "add", "productos", "Falla", "--url", "{{base_url}}/missing")

    assert json.loads(cli("run", "Listar")) == {"path": "/api/productos", "auth": "Bearer s3cret"}
    assert "200 OK" in cli.err
    included = cli("run", "Crear", "-i")
    assert included.startswith("HTTP/1.0 201 Created") and '"nombre": "Monitor"' in included
    cli("run", "Falla")
    cli("run", "Falla", "--fail", expect=1)
    cli("run", "Listar", "--no-history")

    history = json.loads(cli("history", "ls", "--json"))
    assert [h["status"] for h in history] == [404, 404, 201, 200]
    assert "s3cret" not in json.dumps(history)

    assert "s3cret" not in cli("curl", "Listar")
    assert "Bearer s3cret" in cli("curl", "Listar", "--show-secrets")
    cli("history", "clear", "-y")
    assert json.loads(cli("history", "ls", "--json")) == []


def test_run_reports_missing_variables(cli):
    cli("collection", "add", "Productos")
    cli("request", "add", "productos", "Ver", "--url", "{{base_url}}/x/{{nope}}")
    cli("run", "Ver", expect=1)
    assert "nope" in cli.err


def test_import_openapi_and_curl(cli, server):
    cli("var", "set", "base_url", server, "-e", "local")
    preview = cli("import", "openapi", "--dry-run")
    assert "/api/productos  (new)" in preview
    cli("import", "openapi", "--only", "Producto")
    assert [c.name for c in service(cli).collections] == ["Producto"]
    cli("import", "openapi")
    assert "skipped 2" in cli("import", "openapi")
    assert [c.name for c in service(cli).collections] == ["Producto", "Usuario"]

    cli("import", "curl", "producto", stdin=f"curl -X DELETE {server}/api/productos/3 -H 'Authorization: Bearer x'")
    _, request = service(cli).all_requests()[1]
    assert request.method.value == "DELETE" and request.url == "{{base_url}}/api/productos/3"
    assert request.auth.token == "x"


def test_import_openapi_from_file(cli, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"openapi": "3.0.0", "info": {"title": "x", "version": "1"},
                                "paths": {"/api/a": {"post": {"tags": ["a"]}}}}))
    cli("import", "openapi", str(spec))
    assert len(service(cli).all_requests()) == 1
    cli("import", "openapi", str(tmp_path / "nope.json"), expect=1)


def test_settings(cli):
    cli("settings", "set", "network.timeout_seconds", "12")
    cli("settings", "set", "theme", "light")
    cli("settings", "set", "network.verify_ssl", "false")
    settings = json.loads(cli("settings", "ls", "--json"))
    assert settings["network.timeout_seconds"] == 12.0 and settings["theme"] == "light"
    assert settings["network.verify_ssl"] is False
    cli("settings", "set", "theme", "blue", expect=1)
    cli("settings", "set", "nope", "1", expect=1)


def test_no_project_is_a_readable_error(tmp_path):
    err = io.StringIO()
    assert main(["collection", "ls", "-C", str(tmp_path)], out=io.StringIO(), err=err) == 1
    assert "project init" in err.getvalue()
