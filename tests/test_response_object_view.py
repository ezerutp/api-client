"""Response viewer "Object" tab: shown only for JSON bodies, remembered, copies the selected node."""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.models.api_response import ApiResponse
from app.themes.manager import ThemeManager
from app.ui.widgets.response_viewer import ResponseViewer

OBJECT_TAB = 1
GEOJSON = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"magnitud": 3.3}}]}


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["API_CLIENT_DATA_DIR"] = str(tmp_path_factory.mktemp("data"))
    app = QApplication.instance() or QApplication([])
    ThemeManager.instance().apply("dark")
    return app


@pytest.fixture
def viewer(qapp):
    widget = ResponseViewer()
    widget.resize(900, 500)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()


def response(body: bytes, content_type: str) -> ApiResponse:
    return ApiResponse(200, "OK", [("Content-Type", content_type)], body, 12.0, "http://x", "GET")


def json_response(value=GEOJSON) -> ApiResponse:
    return response(json.dumps(value).encode(), "application/geo+json")


def html_response() -> ApiResponse:
    return response(b"<html><body>ArcGIS</body></html>", "text/html")


def top_level_keys(viewer):
    root = viewer.object_view.tree.invisibleRootItem()
    return [root.child(i).text(0) for i in range(root.childCount())]


def test_object_tab_only_for_json(viewer):
    viewer.show_response(json_response())
    assert viewer.tabs.isTabVisible(OBJECT_TAB)
    assert top_level_keys(viewer) == ["type", "features"]

    viewer.show_response(html_response())
    assert not viewer.tabs.isTabVisible(OBJECT_TAB)


def test_object_tab_is_remembered_across_responses(viewer):
    viewer.show_response(json_response())
    viewer.tabs.setCurrentIndex(OBJECT_TAB)

    viewer.show_response(html_response())
    assert viewer.tabs.currentIndex() == 0

    viewer.show_response(json_response({"otro": 1}))
    assert viewer.tabs.currentIndex() == OBJECT_TAB
    assert top_level_keys(viewer) == ["otro"]


def test_body_tab_stays_when_the_user_left_the_object_tab(viewer):
    viewer.show_response(json_response())
    viewer.tabs.setCurrentIndex(OBJECT_TAB)
    viewer.tabs.setCurrentIndex(0)
    viewer.show_response(json_response())
    assert viewer.tabs.currentIndex() == 0


def test_find_and_wrap_hidden_on_object_tab(viewer):
    viewer.show_response(json_response())
    viewer.tabs.setCurrentIndex(OBJECT_TAB)
    assert viewer._search_button.isHidden() and viewer._wrap_button.isHidden()
    viewer.tabs.setCurrentIndex(0)
    assert not viewer._search_button.isHidden() and not viewer._wrap_button.isHidden()


def test_copy_on_object_tab_copies_the_selected_node(viewer, qapp):
    viewer.show_response(json_response())
    viewer.tabs.setCurrentIndex(OBJECT_TAB)
    viewer.object_view.select_path(("features", 0, "properties"))
    viewer.copy_current()
    assert json.loads(QGuiApplication.clipboard().text()) == {"magnitud": 3.3}

    viewer.copy_body()  # "More → Copy body" always copies the whole body
    assert json.loads(QGuiApplication.clipboard().text()) == GEOJSON

    viewer.object_view.select_path(("features", 0, "properties"))
    viewer.tabs.setCurrentIndex(0)
    viewer.copy_current()
    assert json.loads(QGuiApplication.clipboard().text()) == GEOJSON
