"""Body editor "Object view": toggle, split layout and live tree sync."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
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
    widget.activateWindow()
    QTest.qWaitForWindowActive(widget)  # focus assertions need an active window
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


# -- object view <-> editor navigation ------------------------------------------------

PERSONA = """{
  "id": "id",
  "nombre": "ezer",
  "edad": "32",
  "carrera": {
    "id": "01",
    "nombre": "ing",
    "ciclo": "01"
  },
  "update": "2021254222"
}"""


def load(editor, text, qapp):
    editor.set_body(RequestBody(BodyType.JSON, text))
    editor.set_object_view_enabled(True)
    qapp.processEvents()
    return editor.object_view


def item(view, path):
    return view._items[tuple(path)]


def highlighted_line(editor):
    number = editor.editor.navigation_line()
    return editor.editor.document().findBlockByNumber(number - 1).text().strip() if number else None


def cursor_line(editor):
    return editor.editor.textCursor().block().text().strip()


def test_clicking_a_repeated_key_goes_to_the_right_one(editor, qapp):
    view = load(editor, PERSONA, qapp)
    tree = view.tree
    rect = tree.visualItemRect(item(view, ("carrera", "nombre")))
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert highlighted_line(editor) == '"nombre": "ing",'
    assert cursor_line(editor) == '"nombre": "ing",'
    assert editor.editor.textCursor().blockNumber() == 6
    tree.setCurrentItem(item(view, ("nombre",)))
    assert highlighted_line(editor) == '"nombre": "ezer",'


def test_objects_highlight_their_opening_line(editor, qapp):
    view = load(editor, PERSONA, qapp)
    view.tree.setCurrentItem(item(view, ("carrera",)))
    assert highlighted_line(editor) == '"carrera": {'


def test_arrow_keys_in_the_tree_drive_the_editor_without_stealing_focus(editor, qapp):
    view = load(editor, PERSONA, qapp)
    tree = view.tree
    tree.setFocus()
    tree.setCurrentItem(item(view, ("carrera", "id")))
    assert highlighted_line(editor) == '"id": "01",'
    QTest.keyClick(tree, Qt.Key.Key_Down)
    assert highlighted_line(editor) == '"nombre": "ing",'
    QTest.keyClick(tree, Qt.Key.Key_Down)
    assert highlighted_line(editor) == '"ciclo": "01"'
    QTest.keyClick(tree, Qt.Key.Key_Up)
    assert highlighted_line(editor) == '"nombre": "ing",'
    assert not editor.editor.hasFocus()


def test_arrays_of_objects_and_nested_arrays(editor, qapp):
    text = ('{\n  "productos": [\n    {\n      "id": 1,\n      "nombre": "Monitor"\n    },\n    {\n'
            '      "id": 2,\n      "nombre": "Teclado"\n    }\n  ],\n  "m": [[1, 2], [3, [true, null]]]\n}')
    view = load(editor, text, qapp)
    view.tree.setCurrentItem(item(view, ("productos", 1, "nombre")))
    assert highlighted_line(editor) == '"nombre": "Teclado"'
    view.tree.setCurrentItem(item(view, ("productos", 1)))
    assert cursor_line(editor) == "{" and editor.editor.textCursor().blockNumber() == 6
    view.tree.setCurrentItem(item(view, ("m", 1, 1, 1)))
    cursor = editor.editor.textCursor()
    assert cursor.block().text()[cursor.positionInBlock():].startswith("null")


def test_compact_one_line_json_moves_the_cursor_to_the_exact_key(editor, qapp):
    text = '{"nombre":"ezer","carrera":{"nombre":"ing"},"n":[1,{"x":null}]}'
    view = load(editor, text, qapp)
    view.tree.setCurrentItem(item(view, ("carrera", "nombre")))
    assert editor.editor.textCursor().position() == text.index('"nombre":"ing"')
    view.tree.setCurrentItem(item(view, ("n", 1, "x")))
    assert editor.editor.textCursor().position() == text.index('"x"')


def test_double_click_focuses_the_editor(editor, qapp):
    view = load(editor, PERSONA, qapp)
    view.tree.setFocus()
    rect = view.tree.visualItemRect(item(view, ("edad",)))
    # A real double click is press/release + double-click; QTest.mouseDClick sends only the latter.
    QTest.mouseClick(view.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert not editor.editor.hasFocus()
    QTest.mouseDClick(view.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    qapp.processEvents()
    assert cursor_line(editor) == '"edad": "32",'
    assert editor.editor.hasFocus()


def test_far_away_node_is_scrolled_into_view(editor, qapp):
    text = "{\n" + ",\n".join(f'  "k{i}": {i}' for i in range(300)) + "\n}"
    view = load(editor, text, qapp)
    view.tree.setCurrentItem(item(view, ("k250",)))
    qapp.processEvents()
    rect = editor.editor.cursorRect()
    assert editor.editor.viewport().rect().contains(rect)
    assert editor.editor.firstVisibleBlock().blockNumber() > 200


def test_highlight_clears_when_typing(editor, qapp):
    view = load(editor, PERSONA, qapp)
    view.tree.setCurrentItem(item(view, ("edad",)))
    assert editor.editor.navigation_line() is not None
    editor.editor.insertPlainText(" ")
    assert editor.editor.navigation_line() is None


def test_invalid_json_pauses_navigation_and_resumes_when_fixed(editor, qapp):
    view = load(editor, PERSONA, qapp)
    editor.editor.setPlainText(PERSONA[:-2])  # drop the closing brace
    editor._refresh_object_view_later.flush()
    assert "navigation is paused" in view.status.text()
    assert not editor.reveal_path(("carrera", "nombre"))
    view.tree.setCurrentItem(item(view, ("carrera", "nombre")))
    assert editor.editor.navigation_line() is None
    editor.editor.setPlainText(PERSONA)
    editor._refresh_object_view_later.flush()
    assert view.status.isHidden()
    assert editor.reveal_path(("carrera", "nombre"))
    assert highlighted_line(editor) == '"nombre": "ing",'


def test_click_right_after_typing_uses_the_current_text(editor, qapp):
    load(editor, PERSONA, qapp)
    cursor = editor.editor.textCursor()
    cursor.setPosition(1)
    cursor.insertText('\n  "nuevo": 1,')  # debounce still pending: tree not rebuilt yet
    assert editor._refresh_object_view_later.pending
    assert editor.reveal_path(("carrera", "nombre"))
    assert highlighted_line(editor) == '"nombre": "ing",'


def test_editor_cursor_selects_the_tree_node_without_echo(editor, qapp):
    view = load(editor, PERSONA, qapp)
    emitted = []
    view.path_selected.connect(emitted.append)
    editor.editor.setFocus()
    cursor = editor.editor.textCursor()
    cursor.setPosition(PERSONA.index('"ing"') + 2)
    editor.editor.setTextCursor(cursor)
    editor._follow_cursor_later.flush()
    assert view.selected_path() == ("carrera", "nombre")
    # After the trailing comma, still the member of that line.
    cursor.setPosition(PERSONA.index('"01",') + 5)
    editor.editor.setTextCursor(cursor)
    editor._follow_cursor_later.flush()
    assert view.selected_path() == ("carrera", "id")
    assert emitted == []  # the tree did not echo the selection back to the editor
    assert editor.editor.navigation_line() is None


def test_reverse_sync_expands_collapsed_parents(editor, qapp):
    view = load(editor, PERSONA, qapp)
    item(view, ("carrera",)).setExpanded(False)
    editor.editor.setFocus()
    cursor = editor.editor.textCursor()
    cursor.setPosition(PERSONA.index('"ciclo"'))
    editor.editor.setTextCursor(cursor)
    editor._follow_cursor_later.flush()
    assert view.selected_path() == ("carrera", "ciclo")
    assert item(view, ("carrera",)).isExpanded()


def test_tooltip_and_copy_path_share_the_navigation_path(editor, qapp):
    text = '{"productos": [{"precio": 10}, {"precio": 20}]}'
    view = load(editor, text, qapp)
    node = item(view, ("productos", 1, "precio"))
    assert node.toolTip(0) == "Path: productos[1].precio\nType: number"
    assert format_path(node.data(0, Qt.ItemDataRole.UserRole)) == "productos[1].precio"
