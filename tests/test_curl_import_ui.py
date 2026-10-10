"""cURL import from the UI: pasting into the URL bar and the Import cURL dialog."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.models.api_request import BodyType, HttpMethod
from app.models.auth import AuthType
from app.services.project_service import ProjectService, find_api_dir
from app.themes.manager import ThemeManager
from app.ui.dialogs.request_dialogs import CurlImportDialog, NewRequestResult
from tests.test_main_window import make_window

BASE = "http://localhost:8080"
CURL = f"""curl -X POST '{BASE}/api/productos?draft=true' \\
  -H 'Authorization: Bearer t0k3n' \\
  -H 'X-Trace: 1' \\
  --data-raw '{{"nombre":"Monitor"}}'"""


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    ThemeManager.instance().apply("dark")
    return app


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "backend"
    root.mkdir()
    service = ProjectService.create(root, "Backend", BASE)
    collection = service.create_collection("Productos", "/api/productos")
    request = service.create_request(collection.id, "Listar", HttpMethod.GET)
    return root, collection.id, request.id


def reopened_request(root, request_id):
    return ProjectService.open(find_api_dir(root)).service.find_request(request_id)[1]


def test_pasting_curl_in_the_url_bar_fills_the_request(qapp, tmp_path, monkeypatch, project):
    root, _, request_id = project
    window = make_window(tmp_path, monkeypatch)
    window.open_folder(root)
    window.open_request(request_id)
    editor = window.tabs.current_editor()

    mime = QMimeData()
    mime.setText(CURL)
    editor.url_edit.insertFromMimeData(mime)

    assert editor.url_edit.text() == "{{base_url}}/api/productos"
    assert editor.method_combo.currentData() == HttpMethod.POST
    assert [(i.key, i.value) for i in editor.params_editor.items() if i.key] == [("draft", "true")]
    window.flush_saves()
    saved = reopened_request(root, request_id)
    assert saved.name == "Listar"  # the request keeps its identity
    assert saved.method is HttpMethod.POST
    assert saved.auth.type is AuthType.BEARER and saved.auth.token == "t0k3n"
    assert [(h.key, h.value) for h in saved.headers] == [("X-Trace", "1")]
    assert saved.body.type is BodyType.JSON and '"nombre": "Monitor"' in saved.body.content
    window.close()


def test_pasting_a_plain_url_still_works(qapp, tmp_path, monkeypatch, project):
    root, _, request_id = project
    window = make_window(tmp_path, monkeypatch)
    window.open_folder(root)
    window.open_request(request_id)
    editor = window.tabs.current_editor()
    editor.url_edit.set_text("")
    mime = QMimeData()
    mime.setText("  http://x/api/curl  \n")
    editor.url_edit.insertFromMimeData(mime)
    assert editor.url_edit.text() == "http://x/api/curl"
    assert editor.method_combo.currentData() == HttpMethod.GET
    window.close()


def test_import_dialog_creates_a_new_request(qapp, tmp_path, monkeypatch, project):
    root, collection_id, _ = project
    import app.ui.main_window as mw

    seen = {}

    def fake_new_request(parent, collections, selected, initial=None):
        seen["initial"] = initial
        return NewRequestResult("Crear producto", initial.method, collection_id, "", initial.url)

    monkeypatch.setattr(mw.CurlImportDialog, "ask", staticmethod(
        lambda parent, base_url: _accepted_dialog(CURL, base_url)))
    monkeypatch.setattr(mw.NewRequestDialog, "ask", staticmethod(fake_new_request))
    window = make_window(tmp_path, monkeypatch)
    window.open_folder(root)
    window.import_curl()

    assert seen["initial"].name == "productos"
    editor = window.tabs.current_editor()
    created = reopened_request(root, editor.request.id)
    assert created.name == "Crear producto"
    assert created.url == "{{base_url}}/api/productos"
    assert created.auth.token == "t0k3n"
    assert created.body.type is BodyType.JSON
    window.close()


def _accepted_dialog(text, base_url):
    dialog = CurlImportDialog(None, base_url)
    dialog.command.setPlainText(text)
    assert dialog.validate()
    return dialog._result


def test_import_dialog_reports_invalid_commands_and_prefills_from_clipboard(qapp):
    QGuiApplication.clipboard().setText("curl http://x/a")
    dialog = CurlImportDialog(None, "")
    assert dialog.command.toPlainText() == "curl http://x/a"
    dialog.command.setPlainText("wget http://x")
    assert not dialog.validate()
    assert not dialog.error.isHidden()
    dialog.command.setPlainText("curl http://x")
    assert dialog.error.isHidden()
