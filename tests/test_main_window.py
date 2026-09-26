"""End-to-end smoke test of the main window (offscreen, dialogs stubbed)."""

import json
import os
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.models.api_request import HttpMethod
from app.repositories import (
    HistoryRepository, RecentProjectsRepository, SettingsRepository, UiStateRepository,
)
from app.storage.database import Database
from app.themes.manager import ThemeManager
from app.ui.dialogs import base, project_dialogs, request_dialogs
from app.ui.dialogs.request_dialogs import NewRequestResult
from tools import mock_server


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


def make_window(tmp_path, monkeypatch):
    monkeypatch.setenv("API_CLIENT_DATA_DIR", str(tmp_path / "data"))
    from app.ui.main_window import AppContext, MainWindow

    db = Database(tmp_path / "data" / "app.db")
    settings_repo = SettingsRepository(db)
    ctx = AppContext(db, settings_repo, RecentProjectsRepository(db), HistoryRepository(db), UiStateRepository(db),
                     settings_repo.load())
    window = MainWindow(ctx)
    window.show()
    return window


def pump(app, seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_for(app, predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_full_flow_persists_across_restart(qapp, backend, tmp_path, monkeypatch):
    root = tmp_path / "backend-tienda"
    root.mkdir()
    monkeypatch.setattr(base.ConfirmDialog, "ask", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(project_dialogs.CreateProjectDialog, "ask",
                        staticmethod(lambda parent, folder=None: (root, "Backend Tienda", backend)))
    monkeypatch.setattr(request_dialogs.CollectionDialog, "ask",
                        staticmethod(lambda parent, collection=None: ("Productos", "/api/productos")))
    import app.ui.main_window as mw

    monkeypatch.setattr(mw.CollectionDialog, "ask", request_dialogs.CollectionDialog.ask)
    monkeypatch.setattr(mw.NewRequestDialog, "ask", staticmethod(
        lambda parent, collections, selected: NewRequestResult(
            "Crear producto", HttpMethod.POST, collections[0].id, "", "{{base_url}}/api/productos")))

    window = make_window(tmp_path, monkeypatch)
    window.open_folder(root)  # no api-client yet -> confirm -> create dialog
    assert (root / "api-client" / "project.json").exists()
    assert (root / "api-client" / ".gitignore").read_text() == ".secrets.json\n"

    window.new_collection()
    window.new_request(None)
    editor = window.tabs.current_editor()
    assert editor is not None and editor.request.method is HttpMethod.POST
    assert editor.options.currentIndex() == 3  # POST opens the Body tab

    # Edit the body and the auth like a user would, then send.
    editor.body_editor.editor.setPlainText('{\n  "nombre": "Monitor",\n  "precio": 800,\n  "stock": 5\n}')
    editor.auth_editor.type_combo.setCurrentIndex(1)
    editor.auth_editor.token.setText("abc123")
    editor.auth_editor.token.textEdited.emit("abc123")
    editor.send()
    assert wait_for(qapp, lambda: not editor.is_sending)
    assert editor.response._response is not None
    assert editor.response._response.status_code == 201
    assert editor.response._response.json_value["nombre"] == "Monitor"

    # Autosave fires after the debounce.
    assert wait_for(qapp, lambda: not window._dirty, timeout=3)
    stored = json.loads((root / "api-client" / "productos.json").read_text())
    assert stored["requests"][0]["body"]["content"].startswith('{\n  "nombre": "Monitor"')
    assert stored["requests"][0]["auth"] == {"type": "bearer", "token": "abc123"}

    history = window.ctx.history.list(window.service.key)
    assert history and history[0].status_code == 201
    assert "abc123" not in history[0].url

    # Copy as cURL masks the token by default.
    monkeypatch.setattr(window, "_ask_curl_secrets", lambda: "masked")
    window.copy_curl(editor.request.id)
    curl = QGuiApplication.clipboard().text()
    assert "Bearer ****" in curl and "abc123" not in curl

    request_id = editor.request.id
    window.close()
    pump(qapp)

    # Restart: project, tab and content come back exactly as left.
    window2 = make_window(tmp_path, monkeypatch)
    window2.open_last_project_if_enabled()
    reopened = window2.tabs.current_editor()
    assert reopened is not None and reopened.request.id == request_id
    assert reopened.body_editor.editor.toPlainText().startswith('{\n  "nombre": "Monitor"')
    assert reopened.url_edit.text() == "{{base_url}}/api/productos"

    # Duplicate, move, delete.
    window2.duplicate_request(request_id)
    assert len(window2.service.collection("productos").requests) == 2
    copy_id = window2.service.collection("productos").requests[1].id
    window2.delete_request(copy_id)
    assert len(window2.service.collection("productos").requests) == 1
    assert window2.tabs.index_of(copy_id) == -1
    window2.close()


def test_missing_variable_is_reported_without_sending(qapp, tmp_path, monkeypatch):
    from app.services.project_service import ProjectService

    service = ProjectService.create(tmp_path / "p", "P", "http://127.0.0.1:1")
    collection = service.create_collection("Auth")
    request = service.create_request(collection.id, "Me", HttpMethod.GET, "{{base_url}}/me/{{user_id}}")
    window = make_window(tmp_path, monkeypatch)
    window.load_project(service.api_dir)
    window.open_request(request.id)
    editor = window.tabs.current_editor()
    editor.send()
    assert not editor.is_sending
    assert editor.response.stack.currentIndex() == 2
    assert "user_id" in editor.response._error_message.text()
    window.close()


def test_corrupt_collection_is_skipped(qapp, tmp_path, monkeypatch):
    from app.services.project_service import ProjectService

    service = ProjectService.create(tmp_path / "p", "P", "http://x")
    service.create_collection("Buena")
    (service.api_dir / "rota.json").write_text("{ broken")
    warnings = []
    monkeypatch.setattr(base.MessageDialog, "show_warning",
                        staticmethod(lambda parent, title, message, details=(): warnings.extend(details)))
    import app.ui.main_window as mw

    monkeypatch.setattr(mw.MessageDialog, "show_warning", base.MessageDialog.show_warning)
    window = make_window(tmp_path, monkeypatch)
    window.load_project(service.api_dir)
    assert window.service is not None
    assert [c.name for c in window.service.collections] == ["Buena"]
    assert warnings and "rota.json" in warnings[0]
    assert (service.api_dir / "rota.json").read_text() == "{ broken"
    window.close()
