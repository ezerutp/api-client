from __future__ import annotations

import time
from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.models.api_response import ApiResponse
from app.network.errors import ErrorKind, RequestError
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import apply_icon, button, hbox, icon_button, label, vbox
from app.ui.widgets.code_editor import CodeEditor
from app.ui.widgets.json_highlighter import JsonHighlighter
from app.ui.widgets.json_tree_view import JsonTreeView
from app.utils.formatting import format_duration, format_size

_HIGHLIGHT_LIMIT = 1_500_000  # characters; bigger bodies are shown without colors
_DISPLAY_LIMIT = 8_000_000
_BODY_TAB, _OBJECT_TAB = 0, 1


class _FindBar(QFrame):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__()
        self.setObjectName("FindBar")
        self._editor = editor
        self.field = QLineEdit()
        self.field.setPlaceholderText(tr("Find in response"))
        self.field.setProperty("cell", True)
        self.field.setMinimumWidth(200)
        self.field.textChanged.connect(lambda: self.find(from_start=True))
        self.field.returnPressed.connect(self.find)
        self._status = label("", "Faint")
        layout = hbox(
            self.field, self._status,
            icon_button("chevron-down", tr("Next (Enter)"), on_click=self.find, size=14),
            icon_button("close", tr("Close (Esc)"), on_click=self.close_bar, size=14),
            spacing=2, margins=(6, 2, 4, 2),
        )
        self.setLayout(layout)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self.field, activated=self.close_bar)
        self.hide()

    def open(self) -> None:
        self.show()
        selected = self._editor.textCursor().selectedText()
        if selected and " " not in selected:
            self.field.setText(selected)
        self.field.setFocus()
        self.field.selectAll()

    def close_bar(self) -> None:
        self.hide()
        self._editor.setFocus()

    def find(self, from_start: bool = False) -> None:
        text = self.field.text()
        if not text:
            self._status.setText("")
            return
        if from_start:
            cursor = self._editor.textCursor()
            cursor.setPosition(0)
            self._editor.setTextCursor(cursor)
        found = self._editor.find(text)
        if not found:
            cursor = self._editor.textCursor()
            cursor.setPosition(0)
            self._editor.setTextCursor(cursor)
            found = self._editor.find(text)
        self._status.setText("" if found else tr("No results"))


class ResponseViewer(QWidget):
    cancel_requested = Signal()
    retry_requested = Signal()
    notify = Signal(str)
    save_variable_requested = Signal(object, object)  # JSON path, value

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ResponsePanel")
        self._response: ApiResponse | None = None
        self._prefer_object = False  # the user picked the object tab; reopen it for the next JSON response
        self._switching_tab = False
        self._started_at = 0.0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(100)
        self._elapsed_timer.timeout.connect(self._tick)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty())
        self.stack.addWidget(self._build_loading())
        self.stack.addWidget(self._build_error())
        self.stack.addWidget(self._build_response())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.show_empty()

    # -- construction ---------------------------------------------------------------

    def _centered(self, *widgets: QWidget | int) -> QWidget:
        page = QWidget()
        column = vbox(None, *widgets, None, spacing=6)
        for i in range(column.count()):
            item = column.itemAt(i)
            if item.widget() is not None:
                column.setAlignment(item.widget(), Qt.AlignmentFlag.AlignHCenter)
        page.setLayout(column)
        return page

    def _build_empty(self) -> QWidget:
        self._empty_icon = QLabel()
        key = label("Ctrl + Enter", "ShortcutKey")
        hint = QWidget()
        hint.setLayout(hbox(label(tr("Press"), "Faint"), key, label(tr("to send"), "Faint"), spacing=6))
        return self._centered(self._empty_icon, 6, label(tr("Send a request to see the response here."), "EmptyText"), 2, hint)

    def _build_loading(self) -> QWidget:
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedWidth(220)
        self._loading_label = label(tr("Sending request…"), "EmptyTitle")
        self._loading_time = label("0 ms", "Faint")
        cancel = button(tr("Cancel"), "ghost", on_click=self.cancel_requested.emit)
        return self._centered(self._loading_label, self._loading_time, 8, self._progress, 10, cancel)

    def _build_error(self) -> QWidget:
        self._error_icon = QLabel()
        self._error_title = label("", "ErrorTitle")
        self._error_message = label("", "ErrorMessage", wrap=True)
        self._error_hint = label("", "ErrorHint", wrap=True)
        for widget in (self._error_message, self._error_hint):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.setFixedWidth(460)
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._retry = button(tr("Try again"), on_click=self.retry_requested.emit)
        return self._centered(self._error_icon, 4, self._error_title, self._error_message, 2, self._error_hint, 10,
                              self._retry)

    def _build_response(self) -> QWidget:
        page = QWidget()
        self._status_dot = QLabel()
        self._status_text = label("", "StatusText")
        self._time_icon, self._size_icon = QLabel(), QLabel()
        self._time_label = label("", "MetricLabel")
        self._size_label = label("", "MetricLabel")
        self._truncated = label("", "Hint")

        status_bar = QWidget()
        status_bar.setObjectName("ResponseStatusBar")
        status_bar.setLayout(hbox(
            self._status_dot, self._status_text, 18, self._time_icon, self._time_label, 14,
            self._size_icon, self._size_label, 10, self._truncated, None, spacing=6, margins=(14, 8, 14, 8),
        ))

        self.body_view = CodeEditor(read_only=True)
        self._highlighter = JsonHighlighter()
        self._find_bar = _FindBar(self.body_view)
        self._body_message = label("", "EmptyText")
        self._body_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body_stack = QStackedWidget()
        body_editor_page = QWidget()
        body_editor_page.setLayout(vbox(self._find_bar, self.body_view, spacing=6))
        self._body_stack.addWidget(body_editor_page)
        self._body_stack.addWidget(self._centered(self._body_message))

        self.object_view = JsonTreeView()
        self.object_view.can_save_variables = True
        self.object_view.save_variable_requested.connect(self.save_variable_requested)

        self.headers_view = QTextBrowser()
        self.headers_view.setOpenLinks(False)
        self.raw_view = CodeEditor(read_only=True)

        self.tabs = QTabWidget()
        self.tabs.setProperty("tabStyle", "underline")
        self.tabs.setDocumentMode(True)
        for widget, title in ((self._body_stack, tr("Body")), (self.object_view, tr("Object")),
                              (self.headers_view, tr("Headers")), (self.raw_view, tr("Raw"))):
            holder = QWidget()
            holder.setLayout(vbox(widget, margins=(0, 8, 0, 0)))
            self.tabs.addTab(holder, title)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self._copy_button = button(tr("Copy"), "ghost", icon_name="copy", on_click=self.copy_current)
        self._copy_button.setToolTip(tr("Copy response body"))
        self._wrap_button = icon_button("wrap", tr("Toggle word wrap"), size=15)
        self._wrap_button.setCheckable(True)
        self._wrap_button.toggled.connect(self._toggle_wrap)
        self._search_button = icon_button("search", tr("Find (Ctrl+F)"), size=15, on_click=self.open_find)
        self._more_button = icon_button("more", tr("More actions"), size=16)
        self._more_button.setPopupMode(self._more_button.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._more_button)
        menu.addAction(tr("Copy body"), self.copy_body)
        menu.addAction(tr("Copy headers"), self.copy_headers)
        menu.addAction(tr("Copy raw response"), self.copy_raw)
        menu.addSeparator()
        menu.addAction(tr("Save body to file…"), self.save_body)
        self._more_button.setMenu(menu)
        corner = QWidget()
        corner.setLayout(hbox(self._search_button, self._wrap_button, self._copy_button, self._more_button,
                              spacing=2, margins=(0, 0, 0, 4)))
        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, page)
        find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find_shortcut.activated.connect(self.open_find)

        page.setLayout(vbox(status_bar, hbox(self.tabs, margins=(14, 2, 14, 10)), spacing=0))
        return page

    # -- states ---------------------------------------------------------------------

    def show_empty(self) -> None:
        self._elapsed_timer.stop()
        self._response = None
        self.stack.setCurrentIndex(0)

    def show_loading(self) -> None:
        self._started_at = time.perf_counter()
        self._loading_time.setText("0 ms")
        self._elapsed_timer.start()
        self.stack.setCurrentIndex(1)

    def show_error(self, error: RequestError) -> None:
        self._elapsed_timer.stop()
        theme = current_theme()
        cancelled = error.kind is ErrorKind.CANCELLED
        self._error_icon.setPixmap(icons.pixmap("alert-circle" if not cancelled else "close",
                                                theme.text_faint if cancelled else theme.danger, 28))
        self._error_title.setText(error.title)
        self._error_title.setStyleSheet(f"color: {theme.text_muted if cancelled else theme.danger};")
        self._error_message.setText(error.message)
        self._error_hint.setText(error.hint)
        self._error_hint.setVisible(bool(error.hint))
        self._retry.setVisible(error.kind in (
            ErrorKind.CONNECTION_REFUSED, ErrorKind.TIMEOUT, ErrorKind.DNS, ErrorKind.NETWORK,
            ErrorKind.PROTOCOL, ErrorKind.CANCELLED, ErrorKind.SSL,
        ))
        self.stack.setCurrentIndex(2)

    def show_response(self, response: ApiResponse) -> None:
        self._elapsed_timer.stop()
        self._response = response
        theme = current_theme()
        color = theme.status_color(response.status_code)
        self._status_dot.setPixmap(self._dot(color))
        self._status_text.setText(response.status_text)
        self._status_text.setStyleSheet(f"color: {color};")
        self._time_label.setText(format_duration(response.elapsed_ms))
        self._size_label.setText(format_size(response.size_bytes))
        self._size_label.setToolTip(tr("Body: {size}\nHeaders included in total", size=format_size(len(response.body))))
        self._truncated.setText(tr("Body truncated (over 50 MB)") if response.truncated else "")
        self._render_body(response)
        self._render_object(response)
        self._render_headers(response)
        raw = response.raw_text() if response.is_text else response.raw_text().split("\n\n")[0] + "\n\n<binary body>"
        self.raw_view.setPlainText(raw[:_DISPLAY_LIMIT])
        self.stack.setCurrentIndex(3)

    # -- rendering ------------------------------------------------------------------

    def _render_body(self, response: ApiResponse) -> None:
        self._find_bar.hide()
        if not response.body:
            self._body_message.setText(tr("No response body") if response.method != "HEAD" else tr("HEAD responses have no body"))
            self._body_stack.setCurrentIndex(1)
            self._copy_button.setEnabled(False)
            return
        if not response.is_text:
            self._body_message.setText(
                tr("Binary content ({type}, {size}).\nUse More → Save body to file to inspect it.",
                   type=response.content_type or tr("unknown type"), size=format_size(len(response.body)))
            )
            self._body_stack.setCurrentIndex(1)
            self._copy_button.setEnabled(False)
            return
        text = response.pretty_body()
        highlight = response.is_json and len(text) <= _HIGHLIGHT_LIMIT
        self._highlighter.setDocument(None)
        self.body_view.setPlainText(text[:_DISPLAY_LIMIT])
        if highlight:
            self._highlighter.setDocument(self.body_view.document())
        self._body_stack.setCurrentIndex(0)
        self._copy_button.setEnabled(True)

    def _render_object(self, response: ApiResponse) -> None:
        """The object tab exists only for JSON bodies; it reopens if the user was using it."""
        is_json = response.is_json
        if is_json:
            self.object_view.set_value(response.json_value)
        self._switching_tab = True
        try:
            if not is_json and self.tabs.currentIndex() == _OBJECT_TAB:
                self.tabs.setCurrentIndex(_BODY_TAB)  # before hiding it, or Qt jumps to the next tab
            self.tabs.setTabVisible(_OBJECT_TAB, is_json)
            if is_json and self._prefer_object:
                self.tabs.setCurrentIndex(_OBJECT_TAB)
        finally:
            self._switching_tab = False
        self._sync_tab_actions()

    def _render_headers(self, response: ApiResponse) -> None:
        theme = current_theme()

        def rows(pairs: list[tuple[str, str]]) -> str:
            return "".join(
                f"<tr><td style='color:{theme.syntax_key}; padding:3px 18px 3px 0; white-space:nowrap;'>{escape(k)}</td>"
                f"<td style='color:{theme.text}; padding:3px 0;'>{escape(v)}</td></tr>"
                for k, v in pairs
            )

        section = f"color:{theme.text_faint}; font-size:11px; font-weight:600; letter-spacing:.5px;"
        html = (
            f"<div style='{section}'>{tr('RESPONSE HEADERS')} ({len(response.headers)})</div>"
            f"<table cellspacing='0' style='margin:6px 0 16px 0;'>{rows(response.headers)}</table>"
            f"<div style='{section}'>{tr('REQUEST')}</div>"
            f"<table cellspacing='0' style='margin:6px 0 0 0;'>"
            f"{rows([(tr('Method'), response.method), ('URL', response.url), (tr('HTTP version'), response.http_version)])}"
            f"{rows(response.request_headers)}</table>"
        )
        self.headers_view.setHtml(html)

    @staticmethod
    def _dot(color: str):
        from PySide6.QtGui import QColor, QPainter, QPixmap

        size = 10
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, size * 2 - 4, size * 2 - 4)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        return pixmap

    def _tick(self) -> None:
        elapsed = (time.perf_counter() - self._started_at) * 1000
        self._loading_time.setText(format_duration(elapsed))

    # -- actions --------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        if not self._switching_tab:
            self._prefer_object = index == _OBJECT_TAB
        self._sync_tab_actions()

    def _sync_tab_actions(self) -> None:
        on_object = self.tabs.currentIndex() == _OBJECT_TAB
        # The tree has its own navigation; find and wrap only apply to the text views.
        self._search_button.setVisible(not on_object)
        self._wrap_button.setVisible(not on_object)
        self._copy_button.setToolTip(tr("Copy selected value as JSON") if on_object else tr("Copy response body"))

    def open_find(self) -> None:
        if self.stack.currentIndex() == 3 and self._body_stack.currentIndex() == 0:
            self.tabs.setCurrentIndex(_BODY_TAB)
            self._find_bar.open()

    def _toggle_wrap(self, wrap: bool) -> None:
        self.body_view.set_wrap(wrap)
        self.raw_view.set_wrap(wrap)

    def _copy(self, text: str, message: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.notify.emit(message)

    def copy_current(self) -> None:
        """Corner button: the selected node on the object tab, the whole body elsewhere."""
        if self.tabs.currentIndex() == _OBJECT_TAB and self.tabs.isTabVisible(_OBJECT_TAB):
            self.object_view.copy_selected()
            self.notify.emit(tr("Value copied to clipboard"))
        else:
            self.copy_body()

    def copy_body(self) -> None:
        if self._response is not None and self._response.is_text:
            self._copy(self._response.pretty_body(), tr("Response body copied to clipboard"))

    def copy_headers(self) -> None:
        if self._response is not None:
            self._copy("\n".join(f"{k}: {v}" for k, v in self._response.headers), tr("Headers copied to clipboard"))

    def copy_raw(self) -> None:
        if self._response is not None:
            self._copy(self._response.raw_text(), tr("Raw response copied to clipboard"))

    def save_body(self) -> None:
        if self._response is None:
            return
        extension = "json" if self._response.is_json else "txt"
        path, _ = QFileDialog.getSaveFileName(self, tr("Save response body"), f"response.{extension}")
        if path:
            with open(path, "wb") as handle:
                handle.write(self._response.body)
            self.notify.emit(tr("Response saved"))

    def set_font_size(self, size: int) -> None:
        self.body_view.set_font_size(size)
        self.raw_view.set_font_size(size)

    def refresh_theme(self) -> None:
        theme = current_theme()
        self._empty_icon.setPixmap(icons.pixmap("send", theme.text_faint, 30, ))
        self._time_icon.setPixmap(icons.pixmap("clock", theme.text_muted, 14))
        self._size_icon.setPixmap(icons.pixmap("file", theme.text_muted, 14))
        self._copy_button.setIcon(icons.icon("copy", theme.text_muted))
        for widget in (self._wrap_button, self._search_button, self._more_button):
            apply_icon(widget)
        self._highlighter.refresh_theme()
        self.object_view.refresh_theme()
        if self._response is not None:
            self.show_response(self._response)

    def find_text(self, text: str) -> bool:
        return self.body_view.find(text, QTextDocument.FindFlag(0))
