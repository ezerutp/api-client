from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QMenu, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget

from app.models.api_request import ApiRequest
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import apply_icon, hbox, icon_button, set_prop
from app.ui.widgets.request_editor import RequestEditor


class _TabLabel(QWidget):
    close_clicked = Signal()

    def __init__(self, request: ApiRequest) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._dirty = False
        self._hovered = False
        self.method = QLabel()
        self.name = QLabel()
        self.name.setObjectName("TabName")
        self.close_button = QToolButton()
        self.close_button.setObjectName("TabCloseButton")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip("Close (Ctrl+W)")
        self.close_button.clicked.connect(self.close_clicked)
        self.setLayout(hbox(self.method, self.name, 4, self.close_button, spacing=6, margins=(12, 0, 6, 0)))
        self.update_request(request)

    def update_request(self, request: ApiRequest) -> None:
        theme = current_theme()
        self.method.setText(request.method.value)
        self.method.setStyleSheet(f"color: {theme.method_color(request.method.value)}; font-weight: 700; font-size: 11px;")
        name = request.name if len(request.name) <= 28 else request.name[:27] + "…"
        self.name.setText(name)
        self.setToolTip(f"{request.method.value} {request.name}\n{request.url}")
        self._refresh_close_icon()

    def set_active(self, active: bool) -> None:
        set_prop(self.name, "active", active)

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._refresh_close_icon()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._refresh_close_icon()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._refresh_close_icon()

    def _refresh_close_icon(self) -> None:
        theme = current_theme()
        if self._dirty and not self._hovered:
            self.close_button.setIcon(self._dot_icon(theme.text_muted))
            self.close_button.setToolTip("Unsaved changes (saving…)")
        else:
            self.close_button.setIcon(icons.icon("close", theme.text_faint, 13, active_color=theme.text))
            self.close_button.setToolTip("Close (Ctrl+W)")

    @staticmethod
    def _dot_icon(color: str):
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

        pixmap = QPixmap(26, 26)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, 8, 10, 10)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        return QIcon(pixmap)


class RequestTabs(QWidget):
    current_changed = Signal(object)   # RequestEditor | None
    close_requested = Signal(str)      # request id
    new_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("RequestTabBar")
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideNone)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_bar.customContextMenuRequested.connect(self._show_menu)
        self.tab_bar.currentChanged.connect(self._on_current_changed)
        self.tab_bar.tabMoved.connect(self._on_tab_moved)
        self.tab_bar.installEventFilter(self)

        self._new_button = icon_button("plus", "New request (Ctrl+N)", on_click=self.new_requested.emit)
        bar = QWidget()
        bar.setObjectName("RequestTabsBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setLayout(hbox(self.tab_bar, self._new_button, None, spacing=4, margins=(0, 0, 8, 0)))
        bar.setFixedHeight(38)
        self.stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)
        layout.addWidget(self.stack, 1)
        self._editors: list[RequestEditor] = []

    # -- API ------------------------------------------------------------------------

    def count(self) -> int:
        return len(self._editors)

    def editors(self) -> list[RequestEditor]:
        return list(self._editors)

    def current_editor(self) -> RequestEditor | None:
        index = self.tab_bar.currentIndex()
        return self._editors[index] if 0 <= index < len(self._editors) else None

    def index_of(self, request_id: str) -> int:
        return next((i for i, e in enumerate(self._editors) if e.request.id == request_id), -1)

    def editor_for(self, request_id: str) -> RequestEditor | None:
        index = self.index_of(request_id)
        return self._editors[index] if index >= 0 else None

    def add_editor(self, editor: RequestEditor, *, activate: bool = True) -> None:
        label = _TabLabel(editor.request)
        label.close_clicked.connect(lambda e=editor: self.close_requested.emit(e.request.id))
        self._editors.append(editor)
        self.stack.addWidget(editor)
        index = self.tab_bar.addTab("")
        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, label)
        if activate:
            self.tab_bar.setCurrentIndex(index)
        self._refresh_active()

    def activate(self, request_id: str) -> bool:
        index = self.index_of(request_id)
        if index >= 0:
            self.tab_bar.setCurrentIndex(index)
        return index >= 0

    def remove(self, request_id: str) -> RequestEditor | None:
        index = self.index_of(request_id)
        if index < 0:
            return None
        editor = self._editors.pop(index)
        self.stack.removeWidget(editor)
        self.tab_bar.removeTab(index)
        editor.shutdown()
        editor.deleteLater()
        if not self._editors:
            self.current_changed.emit(None)
        self._refresh_active()
        return editor

    def update_request(self, request: ApiRequest) -> None:
        label = self._label(self.index_of(request.id))
        if label is not None:
            label.update_request(request)

    def set_dirty(self, request_id: str, dirty: bool) -> None:
        label = self._label(self.index_of(request_id))
        if label is not None:
            label.set_dirty(dirty)

    def select_relative(self, step: int) -> None:
        if self._editors:
            self.tab_bar.setCurrentIndex((self.tab_bar.currentIndex() + step) % len(self._editors))

    def refresh_theme(self) -> None:
        apply_icon(self._new_button)
        for index, editor in enumerate(self._editors):
            label = self._label(index)
            if label is not None:
                label.update_request(editor.request)
            editor.refresh_theme()

    # -- internals ------------------------------------------------------------------

    def _label(self, index: int) -> _TabLabel | None:
        if index < 0:
            return None
        widget = self.tab_bar.tabButton(index, QTabBar.ButtonPosition.LeftSide)
        return widget if isinstance(widget, _TabLabel) else None

    def _on_current_changed(self, index: int) -> None:
        if 0 <= index < len(self._editors):
            self.stack.setCurrentWidget(self._editors[index])
            self.current_changed.emit(self._editors[index])
        self._refresh_active()

    def _on_tab_moved(self, source: int, target: int) -> None:
        self._editors.insert(target, self._editors.pop(source))

    def _refresh_active(self) -> None:
        current = self.tab_bar.currentIndex()
        for index in range(self.tab_bar.count()):
            label = self._label(index)
            if label is not None:
                label.set_active(index == current)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.tab_bar and event.type() == QEvent.Type.MouseButtonRelease:
            mouse = event if isinstance(event, QMouseEvent) else None
            if mouse is not None and mouse.button() == Qt.MouseButton.MiddleButton:
                index = self.tab_bar.tabAt(mouse.position().toPoint())
                if index >= 0:
                    self.close_requested.emit(self._editors[index].request.id)
                    return True
        return False

    def _show_menu(self, position: QPoint) -> None:
        index = self.tab_bar.tabAt(position)
        if index < 0:
            return
        request_id = self._editors[index].request.id
        menu = QMenu(self)
        menu.addAction("Close", lambda: self.close_requested.emit(request_id))
        menu.addAction("Close others", lambda: self._close_many(lambda e: e.request.id != request_id))
        menu.addAction("Close all", lambda: self._close_many(lambda e: True))
        menu.exec(self.tab_bar.mapToGlobal(position))

    def _close_many(self, predicate) -> None:
        for editor in [e for e in self._editors if predicate(e)]:
            self.close_requested.emit(editor.request.id)
