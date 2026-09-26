"""Floating environment variables window: editing, secrets, environments and main window wiring."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.services.project_service import ProjectService, find_api_dir
from app.themes.manager import ThemeManager
from app.ui.dialogs import variables_window as vw
from app.ui.dialogs.variables_window import GLOBALS, NAME, VALUE, VariablesWindow
from tests.test_main_window import make_window


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    ThemeManager.instance().apply("dark")
    return app


@pytest.fixture
def service(tmp_path):
    service = ProjectService.create(tmp_path, "P", "http://localhost:8080")
    service.set_variable("local", "token", "s3cr3t", secret=True)
    service.set_variable(None, "user_id", "538")
    service.add_environment("prod", "https://prod.example.com")
    return service


@pytest.fixture
def window(qapp, service):
    window = VariablesWindow()
    window.load(service.project, service.secrets, "local", "local")
    emitted = []
    window.changed.connect(emitted.append)
    window.emitted = emitted
    yield window
    window.deleteLater()


def rows(window):
    return [(window.table.item(r, NAME).text(), window.table.item(r, VALUE).text())
            for r in range(window.table.rowCount())]


def reopen(root):
    return ProjectService.open(find_api_dir(root)).service


def test_load_shows_the_selected_scope_and_masks_secrets(window):
    assert window.current_scope == "local"
    assert rows(window) == [("base_url", "http://localhost:8080"), ("token", "s3cr3t")]
    delegate = window.table.itemDelegate()
    option = vw.QStyleOptionViewItem()
    delegate.initStyleOption(option, window.table.model().index(1, VALUE))
    assert option.text == vw._MASK
    window.select_scope(GLOBALS)
    assert rows(window) == [("base_url", "http://localhost:8080"), ("user_id", "538")]


def test_add_variable_by_editing_cells(window):
    window.add_variable()
    row = window.table.rowCount() - 1
    window.table.item(row, NAME).setText("api_key")
    window.table.item(row, VALUE).setText("xyz")
    local_plain, _ = window.emitted[-1].environments["local"]
    assert local_plain["api_key"] == "xyz"


def test_invalid_or_duplicate_names_are_rejected(window):
    window.table.item(0, NAME).setText("token")  # already used in this scope
    assert window.table.item(0, NAME).text() == "base_url"
    window.table.item(0, NAME).setText("1bad name")
    assert window.table.item(0, NAME).text() == "base_url"
    assert window.emitted == []


def test_rename_and_secret_toggle(window):
    window.table.item(1, NAME).setText("access_token")
    window._set_secret(window.variables()[1], False)
    plain, secret = window.emitted[-1].environments["local"]
    assert plain == {"base_url": "http://localhost:8080", "access_token": "s3cr3t"}
    assert secret == {}


def test_delete_asks_first(window, monkeypatch):
    answers = iter([False, True])
    monkeypatch.setattr(vw.ConfirmDialog, "ask", staticmethod(lambda *a, **k: next(answers)))
    window._delete(window.variables()[1])
    assert len(rows(window)) == 2
    window._delete(window.variables()[1])
    assert rows(window) == [("base_url", "http://localhost:8080")]
    assert window.emitted[-1].environments["local"] == ({"base_url": "http://localhost:8080"}, {})


def test_abandoned_new_row_is_dropped(window):
    window.add_variable()
    window.table.closePersistentEditor(window.table.item(window.table.rowCount() - 1, NAME))
    window.table.setCurrentItem(None)
    window._drop_blank_rows()
    assert len(rows(window)) == 2


def test_search_filters_by_name_and_non_secret_value(window):
    window.search.setText("tok")
    assert [window.table.isRowHidden(r) for r in range(2)] == [True, False]
    window.search.setText("s3cr")  # secret values are not searchable
    assert window.stack.currentWidget() is window.empty_label


def test_environment_management(window, monkeypatch):
    names = iter(["QA", "Staging", "qa copy"])
    monkeypatch.setattr(vw.TextInputDialog, "ask", staticmethod(lambda *a, **k: next(names)))
    monkeypatch.setattr(vw.ConfirmDialog, "ask", staticmethod(lambda *a, **k: True))

    window.add_environment()
    assert window.current_scope == "qa"
    window._rename_environment()
    assert window.current_scope == "staging"
    window.select_scope("local")
    window._duplicate_environment()
    assert window.emitted[-1].environments["qa-copy"] == window.emitted[-1].environments["local"]
    window._delete_environment()
    assert window.current_scope == GLOBALS
    assert set(window.emitted[-1].environments) == {"local", "prod", "staging"}


def test_main_window_saves_every_edit(qapp, tmp_path, monkeypatch):
    root = tmp_path / "backend"
    root.mkdir()
    ProjectService.create(root, "Backend", "http://localhost:8080")
    window = make_window(tmp_path, monkeypatch)
    window.open_folder(root)
    assert window.top_bar.variables_button.isVisibleTo(window.top_bar)

    window.top_bar.variables_button.click()
    panel = window._variables_window
    assert panel.isVisible() and panel.current_scope == "local"
    panel.add_variable()
    row = panel.table.rowCount() - 1
    panel.table.item(row, NAME).setText("token")
    panel.table.item(row, VALUE).setText("abc")
    panel._set_secret(panel.variables()[row], True)

    service = reopen(root)
    assert service.secrets.for_environment("local") == {"token": "abc"}
    assert "token" not in service.project.environments["local"].variables
    assert window.variable_context().is_secret("token")

    panel.select_scope(GLOBALS)
    monkeypatch.setattr(vw.ConfirmDialog, "ask", staticmethod(lambda *a, **k: True))
    panel._delete(panel.variables()[0])  # the global base_url
    assert reopen(root).project.base_url == ""

    window.close_project()
    assert not panel.isVisible()
    window.close()
