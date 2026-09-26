"""Save a response value as a {{variable}}: helpers, service, dialog and main window flow."""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.models.api_request import HttpMethod
from app.models.api_response import ApiResponse
from app.services.project_service import ProjectService, find_api_dir
from app.services.variable_service import looks_secret, suggest_variable_name, variable_text
from app.themes.manager import ThemeManager
from app.ui.dialogs.variable_dialogs import SaveVariableDialog, SaveVariableResult
from tests.test_main_window import make_window


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    ThemeManager.instance().apply("dark")
    return app


@pytest.fixture
def service(tmp_path):
    service = ProjectService.create(tmp_path, "P", "http://localhost:8080")
    service.add_environment("prod", "https://prod.example.com")
    return service


def reopen(root):
    return ProjectService.open(find_api_dir(root)).service


def test_helpers():
    assert suggest_variable_name(("data", "access_token")) == "access_token"
    assert suggest_variable_name(("items", 0)) == "items"
    assert suggest_variable_name(("user id",)) == "user_id"
    assert suggest_variable_name(("1st",)) == "_1st"
    assert suggest_variable_name(()) == "value"
    assert variable_text("abc") == "abc"
    assert variable_text(42) == "42"
    assert variable_text(True) == "true"
    assert variable_text(None) == "null"
    assert variable_text({"a": [1, "é"]}) == '{"a":[1,"é"]}'
    assert looks_secret("access_token") and looks_secret("apiKey") and looks_secret("PASSWORD")
    assert not looks_secret("id") and not looks_secret("nombre")


def test_set_variable_in_environment_and_globals(service, tmp_path):
    service.set_variable("local", "user_id", "7")
    service.set_variable(None, "tenant", "acme")
    again = reopen(tmp_path)
    assert again.project.environments["local"].variables["user_id"] == "7"
    assert again.project.variables["tenant"] == "acme"
    context = again.variable_context("local")
    assert context.values["user_id"] == "7" and context.values["tenant"] == "acme"
    assert "user_id" not in again.variable_context("prod").values


def test_secret_replaces_the_plain_copy_and_back(service, tmp_path):
    service.set_variable("local", "token", "plain")
    service.set_variable("local", "token", "s3cr3t", secret=True)
    again = reopen(tmp_path)
    assert "token" not in again.project.environments["local"].variables
    assert again.secrets.for_environment("local") == {"token": "s3cr3t"}
    assert again.variable_context("local").is_secret("token")
    assert ".secrets.json" in (find_api_dir(tmp_path) / ".gitignore").read_text()
    assert "s3cr3t" not in (find_api_dir(tmp_path) / "project.json").read_text()

    again.set_variable("local", "token", "visible")
    final = reopen(tmp_path)
    assert final.project.environments["local"].variables["token"] == "visible"
    assert final.secrets.for_environment("local") == {}


def test_global_base_url_goes_to_the_project_default(service, tmp_path):
    service.set_variable(None, "base_url", "http://new")
    assert reopen(tmp_path).project.base_url == "http://new"


def test_unknown_environment_is_rejected(service):
    with pytest.raises(KeyError):
        service.set_variable("staging", "x", "1")


def test_dialog_defaults_notices_and_validation(qapp, service):
    service.set_variable("local", "token", "old")
    dialog = SaveVariableDialog(None, service.project, service.secrets, "local", "token", "eyJ.abc")
    assert dialog.scope.currentData() == "local"
    assert dialog.secret.isChecked()
    assert "eyJ" not in dialog.preview.text()  # masked while marked as secret
    assert not dialog.notice.isHidden() and "{{token}}" in dialog.notice.text()

    dialog.scope.setCurrentIndex(dialog.scope.findData(None))  # globals, shadowed by "local"
    assert "{{token}}" in dialog.notice.text()

    dialog.secret.setChecked(False)
    assert "eyJ.abc" in dialog.preview.text()
    dialog.name.setText("1 bad name")
    assert not dialog.validate()
    dialog.name.setText("user.id")
    assert dialog.validate()
    assert dialog.result_value() == SaveVariableResult(None, "user.id", False)


def test_saving_from_the_response_object_tab(qapp, tmp_path, monkeypatch):
    root = tmp_path / "backend"
    root.mkdir()
    service = ProjectService.create(root, "Backend", "http://localhost:8080")
    collection = service.create_collection("Auth")
    login = service.create_request(collection.id, "Login", HttpMethod.POST)
    import app.ui.main_window as mw

    asked = {}

    def fake_ask(parent, project, secrets, current, name, value):
        asked.update(current=current, name=name, value=value)
        return SaveVariableResult(current, name, True)

    monkeypatch.setattr(mw.SaveVariableDialog, "ask", staticmethod(fake_ask))
    window = make_window(tmp_path, monkeypatch)
    window.open_folder(root)
    window.open_request(login.id)
    editor = window.tabs.current_editor()
    body = {"data": {"access_token": "eyJ.abc", "expires": 3600}}
    editor.response.show_response(ApiResponse(200, "OK", [("Content-Type", "application/json")],
                                              json.dumps(body).encode(), 5, "http://x", "POST"))
    tree = editor.response.object_view
    assert tree.can_save_variables
    tree.save_variable_requested.emit(("data", "access_token"), "eyJ.abc")

    assert asked == {"current": "local", "name": "access_token", "value": "eyJ.abc"}
    assert reopen(root).secrets.for_environment("local") == {"access_token": "eyJ.abc"}
    assert editor.url_edit.variable_context.is_defined("access_token")  # open editors see it right away
    window.close()


def test_body_editor_tree_does_not_offer_saving(qapp):
    from app.ui.widgets.body_editor import BodyEditor

    assert not BodyEditor().object_view.can_save_variables
