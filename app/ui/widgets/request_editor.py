"""Editor for one open request: request bar, options tabs and response panel."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.models.api_request import ApiRequest, BodyType, HttpMethod, PathParameter, RequestHeader, RequestParameter
from app.models.api_response import ApiResponse
from app.network.errors import ErrorKind, RequestError
from app.network.request_worker import RequestWorker
from app.services.http_client_service import HttpClientService
from app.services.request_builder import PreparedRequest, RequestBuilder, extract_path_param_names
from app.services.variable_service import VariableContext
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import hbox, label, set_prop, vbox
from app.ui.widgets.auth_editor import AuthEditor
from app.ui.widgets.body_editor import BodyEditor
from app.ui.widgets.key_value_editor import COMMON_HEADER_VALUES, COMMON_HEADERS, KeyValueEditor, KvItem
from app.ui.widgets.response_viewer import ResponseViewer
from app.ui.widgets.url_edit import UrlEdit

TAB_PARAMS, TAB_HEADERS, TAB_AUTH, TAB_BODY = range(4)


class RequestEditor(QWidget):
    changed = Signal(str)                    # request id; request object already updated
    finished = Signal(str, object, object)   # request id, PreparedRequest, ApiResponse | RequestError
    sending_changed = Signal(bool)
    duplicate_requested = Signal(str)
    copy_curl_requested = Signal(str)
    notify = Signal(str)
    splitter_moved = Signal(list)

    def __init__(
        self,
        request: ApiRequest,
        http: HttpClientService,
        context_provider: Callable[[], VariableContext],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.request = request
        self._http = http
        self._context_provider = context_provider
        self._worker: RequestWorker | None = None
        self._loading = False

        self._build_request_bar()
        self._build_options()
        self.response = ResponseViewer()
        self.response.cancel_requested.connect(self.cancel)
        self.response.retry_requested.connect(self.send)
        self.response.notify.connect(self.notify)

        top = QWidget()
        top.setObjectName("RequestPanel")
        top_layout = vbox(self._request_bar, self.options, spacing=10, margins=(14, 12, 14, 8))
        top_layout.setStretch(1, 1)
        top.setLayout(top_layout)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setObjectName("EditorSplitter")
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(top)
        self.splitter.addWidget(self.response)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.splitterMoved.connect(lambda *_: self.splitter_moved.emit(self.splitter.sizes()))
        top.setMinimumHeight(170)
        self.response.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
        self.load(request)
        self.set_variable_context(context_provider())
        self.refresh_theme()

    # -- construction ---------------------------------------------------------------

    def _build_request_bar(self) -> None:
        self.method_combo = QComboBox()
        self.method_combo.setObjectName("MethodCombo")
        self.method_combo.setFixedWidth(108)
        for method in HttpMethod:
            self.method_combo.addItem(method.value, method)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)

        self.url_edit = UrlEdit()
        self.url_edit.text_changed.connect(self._on_url_changed)
        self.url_edit.submitted.connect(self.send)

        self.send_button = QPushButton(tr("Send"))
        self.send_button.setObjectName("SendButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setMinimumWidth(92)
        self.send_button.clicked.connect(self._on_send_clicked)

        self.send_menu_button = QToolButton()
        self.send_menu_button.setObjectName("SendMenuButton")
        self.send_menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_menu_button.setToolTip(tr("More actions"))
        self.send_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.send_menu_button)
        menu.addAction(tr("Copy URL"), self.copy_url)
        menu.addAction(tr("Copy as cURL"), lambda: self.copy_curl_requested.emit(self.request.id))
        menu.addSeparator()
        menu.addAction(tr("Duplicate request"), lambda: self.duplicate_requested.emit(self.request.id))
        menu.addAction(tr("Format JSON body"), self.format_body)
        self.send_menu_button.setMenu(menu)

        send_group = QWidget()
        send_group.setLayout(hbox(self.send_button, self.send_menu_button, spacing=0))
        self._request_bar = QWidget()
        self._request_bar.setObjectName("RequestBar")
        self._request_bar.setLayout(hbox(self.method_combo, self.url_edit, send_group, spacing=8))
        self._request_bar.setFixedHeight(40)

    def _build_options(self) -> None:
        self.params_editor = KeyValueEditor(key_placeholder=tr("Key"), value_placeholder=tr("Value"), scrollable=False)
        self.path_editor = KeyValueEditor(key_placeholder=tr("Path variable"), value_placeholder=tr("Value"),
                                          fixed_keys=True, scrollable=False)
        self.headers_editor = KeyValueEditor(key_placeholder=tr("Header"), value_placeholder=tr("Value"),
                                             key_completions=COMMON_HEADERS, value_completions=COMMON_HEADER_VALUES)
        self.auth_editor = AuthEditor()
        self.body_editor = BodyEditor()

        self._path_section = QWidget()
        self._path_section.setLayout(vbox(label(tr("PATH VARIABLES"), "SectionLabel"), self.path_editor, spacing=6,
                                          margins=(0, 14, 0, 0)))
        self.url_preview = label("", "UrlPreview")
        self.url_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url_preview.setWordWrap(True)
        params_content = QWidget()
        params_content.setLayout(vbox(
            label(tr("QUERY PARAMETERS"), "SectionLabel"), self.params_editor, self._path_section, 12,
            self.url_preview, None, spacing=6, margins=(0, 10, 4, 0),
        ))
        params_scroll = QScrollArea()
        params_scroll.setWidgetResizable(True)
        params_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        params_scroll.setWidget(params_content)

        headers_page = QWidget()
        headers_page.setLayout(vbox(self.headers_editor, spacing=0, margins=(0, 10, 0, 0)))

        self.options = QTabWidget()
        self.options.setProperty("tabStyle", "underline")
        self.options.setDocumentMode(True)
        self.options.addTab(params_scroll, tr("Params"))
        self.options.addTab(headers_page, tr("Headers"))
        self.options.addTab(self.auth_editor, tr("Auth"))
        self.options.addTab(self.body_editor, tr("Body"))

        self.params_editor.changed.connect(self._on_params_changed)
        self.path_editor.changed.connect(self._on_params_changed)
        self.headers_editor.changed.connect(self._on_headers_changed)
        self.auth_editor.changed.connect(self._on_auth_changed)
        self.body_editor.changed.connect(self._on_body_changed)

    # -- loading & saving -----------------------------------------------------------

    def load(self, request: ApiRequest) -> None:
        self._loading = True
        self.request = request
        self.method_combo.setCurrentIndex(list(HttpMethod).index(request.method))
        self.url_edit.set_text(request.url)
        self.params_editor.set_items([KvItem(p.key, p.value, p.enabled) for p in request.params])
        self.headers_editor.set_items([KvItem(h.key, h.value, h.enabled) for h in request.headers])
        self.auth_editor.set_auth(request.auth)
        self.body_editor.set_body(request.body)
        self._sync_path_params()
        self._loading = False
        self._update_method_style()
        self._update_tab_titles()
        self._update_url_preview()

    def _emit_changed(self) -> None:
        if not self._loading:
            self._update_tab_titles()
            self._update_url_preview()
            self.changed.emit(self.request.id)

    def _on_method_changed(self) -> None:
        self._update_method_style()
        if self._loading:
            return
        self.request.method = HttpMethod(self.method_combo.currentData())
        self._emit_changed()

    def _on_url_changed(self, text: str) -> None:
        if self._loading:
            return
        self.request.url = text
        self._sync_path_params()
        self._emit_changed()

    def _on_params_changed(self) -> None:
        if self._loading:
            return
        self.request.params = [RequestParameter(i.key, i.value, i.enabled) for i in self.params_editor.items()]
        self.request.path_params = [PathParameter(i.key, i.value, i.enabled) for i in self.path_editor.items()]
        self._emit_changed()

    def _on_headers_changed(self) -> None:
        if self._loading:
            return
        self.request.headers = [RequestHeader(i.key, i.value, i.enabled) for i in self.headers_editor.items()]
        self._emit_changed()

    def _on_auth_changed(self) -> None:
        if self._loading:
            return
        self.auth_editor.apply_to(self.request.auth)
        self._emit_changed()

    def _on_body_changed(self) -> None:
        if self._loading:
            return
        self.body_editor.apply_to(self.request.body)
        self._emit_changed()

    def _sync_path_params(self) -> None:
        """Keep the path variable rows in sync with ``{name}`` placeholders in the URL."""
        names = extract_path_param_names(self.request.url)
        existing = {p.key: p for p in self.request.path_params}
        synced = [existing.get(n) or PathParameter(n, "", True) for n in names]
        changed = [p.key for p in synced] != [p.key for p in self.request.path_params]
        self.request.path_params = synced
        if changed or self._loading:
            was_loading = self._loading
            self._loading = True
            self.path_editor.set_items([KvItem(p.key, p.value, p.enabled) for p in synced])
            self._loading = was_loading
        self._path_section.setVisible(bool(synced))

    # -- appearance -----------------------------------------------------------------

    def _update_method_style(self) -> None:
        method = HttpMethod(self.method_combo.currentData())
        set_prop(self.method_combo, "method", method.value)
        theme = current_theme()
        for index, m in enumerate(HttpMethod):
            self.method_combo.setItemData(index, QColor(theme.method_color(m.value)), Qt.ItemDataRole.ForegroundRole)

    def _update_tab_titles(self) -> None:
        def title(base: str, count: int) -> str:
            return f"{base}  {count}" if count else base

        self.options.setTabText(TAB_PARAMS, title(tr("Params"), self.params_editor.active_count()
                                                  + len(self.request.path_params)))
        self.options.setTabText(TAB_HEADERS, title(tr("Headers"), self.headers_editor.active_count()))
        auth_type = self.request.auth.type
        self.options.setTabText(TAB_AUTH, tr("Auth") if auth_type.value == "none" else tr("Auth") + "  •")
        self.options.setTabText(TAB_BODY, tr("Body") if self.request.body.type is BodyType.NONE else tr("Body") + "  •")

    def _update_url_preview(self) -> None:
        try:
            url = RequestBuilder(self._context_provider()).build_url(self.request)
        except RequestError as error:
            if error.kind is ErrorKind.INVALID_URL and not self.request.url.strip():
                self.url_preview.setText("")
                return
            self.url_preview.setText("⚠  " + error.message.splitlines()[0])
            self.url_preview.setStyleSheet(f"color: {current_theme().warning};")
            return
        except Exception:  # the preview must never break editing
            self.url_preview.setText("")
            return
        masked = PreparedRequest("GET", url, [], None, self._context_provider().secret_values()).masked_url
        self.url_preview.setText(f"→  {masked}")
        self.url_preview.setStyleSheet("")

    def set_variable_context(self, context: VariableContext) -> None:
        self.url_edit.set_variable_context(context)
        self._update_url_preview()

    def set_font_size(self, size: int) -> None:
        self.body_editor.set_font_size(size)
        self.response.set_font_size(size)

    def refresh_theme(self) -> None:
        theme = current_theme()
        self.send_menu_button.setIcon(icons.icon("chevron-down", theme.accent_text, 14))
        self._update_method_style()
        self.url_edit.refresh_theme()
        self.body_editor.refresh_theme()
        self.auth_editor.refresh_theme()
        self.response.refresh_theme()
        for editor in (self.params_editor, self.path_editor, self.headers_editor):
            editor.refresh_theme()

    # -- focus helpers --------------------------------------------------------------

    def focus_url(self, select_all: bool = True) -> None:
        if select_all:
            self.url_edit.select_all_and_focus()
        else:
            self.url_edit.setFocus()
            self.url_edit.move_cursor_to_end()

    def open_default_tab(self) -> None:
        self.options.setCurrentIndex(TAB_BODY if self.request.method.usually_has_body else TAB_PARAMS)

    def format_body(self) -> bool:
        if self.request.body.type is not BodyType.JSON:
            return False
        self.options.setCurrentIndex(TAB_BODY)
        ok = self.body_editor.format()
        if not ok:
            self.notify.emit(tr("Body is not valid JSON — nothing to format"))
        return ok

    def splitter_sizes(self) -> list[int]:
        return self.splitter.sizes()

    def set_splitter_sizes(self, sizes: list[int]) -> None:
        if len(sizes) == 2 and all(s > 0 for s in sizes):
            self.splitter.setSizes(sizes)

    # -- sending --------------------------------------------------------------------

    @property
    def is_sending(self) -> bool:
        return self._worker is not None

    def prepare(self) -> PreparedRequest:
        return self._http.prepare(self.request, self._context_provider())

    def _on_send_clicked(self) -> None:
        self.cancel() if self.is_sending else self.send()

    def send(self) -> None:
        if self.is_sending:
            return
        self.body_editor.show_error_line(None)
        try:
            prepared = self.prepare()
        except RequestError as error:
            if error.kind is ErrorKind.INVALID_JSON:
                self.options.setCurrentIndex(TAB_BODY)
                self.body_editor.show_error_line(error.line)
            self.response.show_error(error)
            return
        worker = RequestWorker(self._http, prepared)
        worker.signals.finished.connect(lambda response, w=worker: self._on_finished(w, response))
        worker.signals.failed.connect(lambda error, w=worker: self._on_failed(w, error))
        self._worker = worker
        self._set_sending(True)
        self.response.show_loading()
        QThreadPool.globalInstance().start(worker)

    def cancel(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.cancel()
        self._worker = None
        self._set_sending(False)
        self.response.show_error(RequestError(ErrorKind.CANCELLED, tr("Request cancelled"),
                                              tr("The request was cancelled before a response arrived."), ""))

    def _on_finished(self, worker: RequestWorker, response: ApiResponse) -> None:
        if worker is not self._worker:
            return  # cancelled or superseded
        self._worker = None
        self._set_sending(False)
        self.response.show_response(response)
        self.finished.emit(self.request.id, worker.prepared, response)

    def _on_failed(self, worker: RequestWorker, error: RequestError) -> None:
        if worker is not self._worker:
            return
        self._worker = None
        self._set_sending(False)
        self.response.show_error(error)
        self.finished.emit(self.request.id, worker.prepared, error)

    def _set_sending(self, sending: bool) -> None:
        self.send_button.setText(tr("Cancel") if sending else tr("Send"))
        set_prop(self.send_button, "sending", sending)
        self.send_menu_button.setEnabled(not sending)
        self.sending_changed.emit(sending)

    def copy_url(self) -> None:
        try:
            url = RequestBuilder(self._context_provider()).build_url(self.request)
        except RequestError:
            url = self.request.url
        QGuiApplication.clipboard().setText(url)
        self.notify.emit(tr("URL copied to clipboard"))

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
