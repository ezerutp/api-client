"""Body editor "Object view": toggle, split layout and live tree sync."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.models.api_request import BodyType, RequestBody
from app.services.json_service import JsonVariable
from app.themes.manager import ThemeManager
from app.ui.widgets.body_editor import BodyEditor
from app.ui.widgets.json_tree_view import format_path, summarize, to_json

DOC = '{\n  "id": "id",\n  "nombre": "ezer",\n  "carrera": {"id": "01", "ciclo": "01"},\n  "tags": [1, true, null]\n}'


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["API_CLIENT_DATA_DIR"] = str(tmp_path_factory.mktemp("data"))
    app = QApplication.instance() or QApplication([])
    ThemeManager.instance().apply("dark")
    return app


@pytest.fixture
def editor(qapp):
    widget = BodyEditor()
    widget.resize(1000, 400)
    widget.set_body(RequestBody(BodyType.JSON, DOC))
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()


def rows(tree_view):
    root = tree_view.tree.invisibleRootItem()
    return [(root.child(i).text(0), root.child(i).text(1)) for i in range(root.childCount())]


def test_hidden_by_default_and_editor_takes_full_width(editor):
    assert editor.object_view_toggle.isVisible()
    assert not editor.object_view.isVisible()


def test_toggle_splits_three_to_one_and_builds_tree(editor, qapp):
    emitted = []
    editor.object_view_toggled.connect(emitted.append)
    editor.object_view_toggle.click()
    qapp.processEvents()
    assert emitted == [True]
    assert editor.object_view.isVisible()
    left, right = editor.editor_split.sizes()
    assert 2.5 < left / right < 3.5
    assert rows(editor.object_view) == [
        ("id", '"id"'), ("nombre", '"ezer"'), ("carrera", "{ 2 fields }"), ("tags", "[ 3 items ]"),
    ]
    carrera = editor.object_view.tree.invisibleRootItem().child(2)
    assert carrera.isExpanded() and carrera.child(1).text(0) == "ciclo"


def test_tree_follows_edits_after_debounce_and_keeps_last_valid(editor, qapp):
    editor.set_object_view_enabled(True)
    editor.editor.setPlainText('{"a": 1}')
    assert editor._refresh_object_view_later.pending
    editor._refresh_object_view_later.flush()
    assert rows(editor.object_view) == [("a", "1")]

    editor.editor.setPlainText('{"a": 1,')
    editor._refresh_object_view_later.flush()
    assert rows(editor.object_view) == [("a", "1")]
    assert not editor.object_view.status.isHidden()

    editor.editor.setPlainText('{"b": {{token}}}')
    editor._refresh_object_view_later.flush()
    assert rows(editor.object_view) == [("b", "{{token}}")]
    assert editor.object_view.status.isHidden()


def test_collapsed_nodes_stay_collapsed_after_rebuild(editor):
    editor.set_object_view_enabled(True)
    tree = editor.object_view.tree
    tree.invisibleRootItem().child(2).setExpanded(False)
    editor.editor.setPlainText(DOC.replace('"ezer"', '"otro"'))
    editor._refresh_object_view_later.flush()
    assert not tree.invisibleRootItem().child(2).isExpanded()
    assert tree.invisibleRootItem().child(3).isExpanded()


def test_toggle_hidden_for_non_json_bodies(editor):
    editor.set_object_view_enabled(True)
    editor.set_body(RequestBody(BodyType.TEXT, "hola"))
    assert not editor.object_view_toggle.isVisible()
    assert not editor.object_view.isVisible()


def test_helpers():
    assert format_path(("carrera", "id")) == "carrera.id"
    assert format_path(("items", 0, "a b")) == 'items[0]["a b"]'
    assert summarize({"a": 1}) == "{ 1 field }"
    assert to_json({"id": JsonVariable("{{id}}"), "n": "x"}) == '{\n  "id": {{id}},\n  "n": "x"\n}'
