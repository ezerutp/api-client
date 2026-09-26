"""OpenAPI 3 import: parsing, sample bodies, re-import rules, preview dialog and main window flow."""

import copy
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from app.models.api_request import BodyType, HttpMethod
from app.models.auth import AuthType
from app.models.settings import NetworkSettings
from app.services.http_client_service import HttpClientService
from app.services.openapi_service import (
    OpenApiError,
    common_base_path,
    humanize,
    normalize_path,
    parse_openapi,
)
from app.services.project_service import ProjectService, find_api_dir
from app.services.variable_service import VariableContext
from app.themes.manager import ThemeManager
from app.ui.dialogs.openapi_dialog import OpenApiImportDialog
from tests.test_main_window import make_window
from tools import mock_server
from tools.mock_server import OPENAPI_SPEC


def spec(**changes):
    data = copy.deepcopy(OPENAPI_SPEC)
    data.update(changes)
    return data


def parse(data):
    return parse_openapi(json.dumps(data))


def by_name(result):
    return {e.request.name: e for e in result.endpoints}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    ThemeManager.instance().apply("dark")
    return app


@pytest.fixture
def backend():
    server = ThreadingHTTPServer(("127.0.0.1", 0), mock_server.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


# -- parsing ------------------------------------------------------------------------

def test_springdoc_spec_becomes_collections_per_controller():
    result = parse(OPENAPI_SPEC)
    assert (result.title, result.version) == ("Tienda API", "v1")
    assert {name: len(items) for name, items in result.collections().items()} == {
        "Producto": 5, "Usuario": 2, "Auth": 1}
    endpoints = by_name(result)

    listing = endpoints["Listar productos"].request
    assert (listing.method, listing.url) == (HttpMethod.GET, "{{base_url}}/api/productos")
    assert [(p.key, p.value, p.enabled) for p in listing.params] == [
        ("page", "0", False), ("size", "20", False), ("sort", "nombre", False)]

    detail = endpoints["Obtener producto"].request
    assert detail.url == "{{base_url}}/api/productos/{id}"
    assert [p.key for p in detail.path_params] == ["id"]

    create = endpoints["Crear producto"].request
    assert create.auth.type is AuthType.BEARER and create.auth.token == "{{token}}"
    assert create.body.type is BodyType.JSON
    assert json.loads(create.body.content) == {"nombre": "Monitor", "precio": 350, "stock": 5}  # readOnly id left out

    assert json.loads(endpoints["Crear usuario"].request.body.content) == {"nombre": "string",
                                                                            "email": "user@example.com"}
    assert json.loads(endpoints["Iniciar sesión"].request.body.content) == {"username": "admin", "password": "admin"}
    assert endpoints["Iniciar sesión"].request.auth.type is AuthType.NONE


def test_server_context_path_is_kept():
    result = parse(spec(servers=[{"url": "http://localhost:8080/tienda/"}]))
    assert by_name(result)["Listar productos"].request.url == "{{base_url}}/tienda/api/productos"
    assert parse(spec(servers=[{"url": "/v2"}])).endpoints[0].path == "/v2/api/productos"
    assert parse(spec(servers=[{"url": "{scheme}://host/{base}"}])).endpoints[0].path == "/api/productos"


def test_sample_bodies_follow_the_schema():
    schemas = {
        "Categoria": {"type": "object", "properties": {"nombre": {"type": "string"},
                                                        "padre": {"$ref": "#/components/schemas/Categoria"}}},
        "Pedido": {"allOf": [
            {"type": "object", "properties": {"id": {"type": "string", "format": "uuid"}}},
            {"type": "object", "properties": {
                "estado": {"type": "string", "enum": ["NUEVO", "PAGADO"]},
                "fecha": {"type": "string", "format": "date-time"},
                "items": {"type": "array", "items": {"type": "integer"}},
                "nota": {"type": ["string", "null"]},
                "pago": {"oneOf": [{"type": "boolean"}, {"type": "string"}]},
                "categoria": {"$ref": "#/components/schemas/Categoria"},
            }},
        ]},
    }
    data = {"openapi": "3.1.0", "info": {"title": "x"}, "components": {"schemas": schemas}, "paths": {
        "/pedidos": {"post": {"requestBody": {"content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Pedido"}}}}}}}}
    body = json.loads(parse(data).endpoints[0].request.body.content)
    assert body == {"id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "estado": "NUEVO",
                    "fecha": "2024-01-31T10:00:00Z", "items": [0], "nota": "string", "pago": False,
                    "categoria": {"nombre": "string", "padre": {}}}


def test_untagged_operations_names_and_notes():
    data = {"openapi": "3.0.0", "paths": {
        "/upload": {"post": {"operationId": "subirArchivo_1", "requestBody": {"content": {
            "multipart/form-data": {"schema": {"type": "object"}}}}}},
        "/ping": {"get": {}},
    }}
    result = parse(data)
    assert [(e.collection, e.request.name) for e in result.endpoints] == [
        ("Default", "Subir archivo"), ("Default", "GET /ping")]
    assert result.endpoints[0].request.body.type is BodyType.NONE
    assert "multipart/form-data" in result.notes[0]


def test_security_schemes():
    data = spec()
    data["components"]["securitySchemes"] = {"basic": {"type": "http", "scheme": "basic"},
                                             "key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}}
    data["security"] = [{"key": []}]
    data["paths"]["/api/productos"]["post"]["security"] = [{"basic": []}]
    endpoints = by_name(parse(data))
    assert endpoints["Crear producto"].request.auth.type is AuthType.BASIC
    listing = endpoints["Listar productos"].request  # inherits the global api key
    assert [(h.key, h.value) for h in listing.headers] == [("X-Api-Key", "{{api_key}}")]


@pytest.mark.parametrize("text, message", [
    ("openapi: 3.0.1\ninfo: {}", "YAML"),
    ('{"swagger": "2.0", "paths": {}}', "Swagger 2.0"),
    ("<html>", "not valid JSON"),
    ("[]", "not an OpenAPI document"),
    ('{"openapi": "3.0.0"}', "does not define any paths"),
    ('{"openapi": "3.0.0", "paths": {"/x": {}}}', "does not define any operations"),
])
def test_unusable_specs_are_explained(text, message):
    with pytest.raises(OpenApiError, match=message):
        parse_openapi(text)


def test_helpers():
    assert normalize_path("{{base_url}}/api/productos/{id}?x=1") == "/api/productos/{}"
    assert normalize_path("http://localhost:8080/api/productos/{productId}/") == "/api/productos/{}"
    assert normalize_path("{{base_url}}") == "/"
    assert common_base_path(["/api/productos", "/api/productos/{id}"]) == "/api/productos"
    assert common_base_path(["/api/auth/login"]) == "/api/auth"
    assert common_base_path(["/a", "/b"]) == ""
    assert humanize("producto-controller") == "Producto"
    assert humanize("ProductoController") == "Producto"
    assert humanize("listarProductos_2") == "Listar productos"
    assert humanize("Productos") == "Productos"


# -- storing --------------------------------------------------------------------------

def test_import_creates_collections_and_skips_existing(tmp_path):
    service = ProjectService.create(tmp_path, "P", "http://localhost:8080")
    productos = service.create_collection("Producto", "/api/productos")
    service.create_request(productos.id, "Mi listado", HttpMethod.GET, "{{base_url}}/api/productos?page=3")
    result = parse(OPENAPI_SPEC)
    result.mark_existing(service.collections)
    assert [e.request.name for e in result.endpoints if e.exists] == ["Listar productos"]

    summary = service.import_endpoints(result.endpoints)
    assert (summary.requests, summary.skipped, summary.new_collections) == (7, 1, ["Usuario", "Auth"])
    reopened = ProjectService.open(find_api_dir(tmp_path)).service
    names = {c.name: c for c in reopened.collections}
    assert [r.name for r in names["Producto"].requests] == ["Mi listado", "Crear producto", "Obtener producto",
                                                             "Actualizar producto", "Eliminar producto"]
    assert names["Usuario"].base_path == "/api/usuarios"
    assert names["Auth"].base_path == "/api/auth"

    again = service.import_endpoints(parse(OPENAPI_SPEC).endpoints)
    assert (again.requests, again.skipped) == (0, 8)


# -- UI -------------------------------------------------------------------------------

def make_dialog(collections=(), context=None):
    http = HttpClientService(lambda: NetworkSettings())
    return OpenApiImportDialog(None, http, context or VariableContext(), list(collections))


def test_dialog_preview_and_selection(qapp, tmp_path):
    service = ProjectService.create(tmp_path, "P", "http://localhost:8080")
    auth = service.create_collection("Auth")
    service.create_request(auth.id, "Login", HttpMethod.POST, "{{base_url}}/api/auth/login")
    dialog = make_dialog(service.collections)
    assert not dialog.ok_button.isEnabled()

    dialog.load_text(json.dumps(OPENAPI_SPEC))
    assert dialog.tree.topLevelItemCount() == 3
    assert "8 endpoints, 7 new" in dialog.status.text()
    assert len(dialog.selected_endpoints()) == 7
    auth_item = dialog.tree.topLevelItem(2)
    assert not auth_item.flags() & Qt.ItemFlag.ItemIsEnabled  # everything there already exists

    dialog.tree.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked)  # skip Usuario
    assert len(dialog.selected_endpoints()) == 5
    assert dialog.ok_button.text() == "Import 5 requests"

    dialog.show()
    dialog.url.setFocus()
    qapp.processEvents()
    QTest.keyClick(dialog.url, Qt.Key.Key_Return)  # reloads; must not import the current selection
    assert dialog.result() != QDialog.DialogCode.Accepted and dialog.isVisible()
    dialog.hide()

    dialog.load_text('{"swagger": "2.0"}')
    assert dialog.error.isVisibleTo(dialog) and "Swagger" in dialog.error.text()


def test_dialog_fetches_the_spec_from_the_backend(qapp, backend):
    dialog = make_dialog(context=VariableContext(values={"base_url": backend}))
    dialog.load_url()
    deadline = time.time() + 5
    while dialog.tree.isHidden() and not dialog.error.text() and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert dialog.tree.topLevelItemCount() == 3, dialog.error.text()

    dialog.url.setText("{{nope}}/v3/api-docs")
    dialog.load_url()
    assert "nope" in dialog.error.text()


def test_main_window_imports_into_the_sidebar(qapp, tmp_path, monkeypatch):
    root = tmp_path / "backend"
    root.mkdir()
    ProjectService.create(root, "Backend", "http://localhost:8080")
    import app.ui.main_window as mw

    monkeypatch.setattr(mw.OpenApiImportDialog, "ask",
                        staticmethod(lambda *a, **k: parse(OPENAPI_SPEC).endpoints))
    window = make_window(tmp_path, monkeypatch)
    window.open_folder(root)
    window.import_openapi()
    assert [c.name for c in window.service.collections] == ["Producto", "Usuario", "Auth"]
    assert window.sidebar.model.rowCount() == 3
    assert "8" in window.toast.text()
    window.close()
