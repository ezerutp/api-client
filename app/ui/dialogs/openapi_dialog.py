"""Import requests from an OpenAPI 3 spec: load it (URL or file), preview, pick endpoints."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import QDialog, QFileDialog, QLineEdit, QTreeWidget, QTreeWidgetItem, QWidget

from app.i18n import tr, trn
from app.models.api_request import ApiRequest, RequestHeader
from app.models.api_response import ApiResponse
from app.models.collection import Collection
from app.network.errors import RequestError
from app.network.request_worker import RequestWorker
from app.services.http_client_service import HttpClientService
from app.services.openapi_service import DEFAULT_SPEC_URL, ImportedEndpoint, OpenApiError, OpenApiImport, parse_openapi
from app.services.variable_service import VariableContext
from app.themes.manager import current_theme
from app.ui.dialogs.base import BaseDialog, field_error_label
from app.ui.helpers import button, hbox, label, monospace_font, set_prop

_ENDPOINT_ROLE = Qt.ItemDataRole.UserRole


class OpenApiImportDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, http: HttpClientService, context: VariableContext,
                 collections: list[Collection], start_dir: Path | None = None) -> None:
        super().__init__(parent, tr("Import OpenAPI"), width=700)
        self._http = http
        self._context = context
        self._collections = collections
        self._start_dir = start_dir
        self._worker: RequestWorker | None = None
        self._result: OpenApiImport | None = None

        self.url = QLineEdit(DEFAULT_SPEC_URL)
        self.url.returnPressed.connect(self.load_url)
        self.url.textChanged.connect(lambda: set_prop(self.url, "invalid", False))
        self.load_button = button(tr("Load"), on_click=self.load_url)
        self.file_button = button(tr("Choose file…"), icon_name="file", on_click=self._choose_file)
        for widget in (self.load_button, self.file_button):
            widget.setAutoDefault(False)
        self.add_field(tr("Spec URL"), layout=hbox(self.url, self.load_button, self.file_button, spacing=6),
                       hint=tr("springdoc-openapi serves the spec at /v3/api-docs. Endpoints that already exist "
                               "(same method and path) are left untouched."))

        self.error = field_error_label()
        self.status = label("", "Hint", wrap=True)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemChanged.connect(lambda *_: self._update_selection())
        self.tree.hide()
        self.content.addWidget(self.error)
        self.content.addWidget(self.status)
        self.content.addWidget(self.tree, 1)
        self.notes = label("", "Hint", wrap=True)
        self.notes.hide()
        self.content.addWidget(self.notes)

        self.ok_button.setText(tr("Import"))
        self.ok_button.setEnabled(False)
        self.url.setFocus()
        self.url.selectAll()

    # -- loading --------------------------------------------------------------------

    def load_url(self) -> None:
        if self._worker is not None:
            return
        request = ApiRequest(name="OpenAPI", url=self.url.text().strip(),
                             headers=[RequestHeader("Accept", "application/json")])
        try:
            prepared = self._http.prepare(request, self._context)
        except RequestError as error:
            self._show_error(error.message)
            set_prop(self.url, "invalid", True)
            return
        worker = RequestWorker(self._http, prepared)
        worker.signals.finished.connect(lambda response, w=worker: self._on_fetched(w, response))
        worker.signals.failed.connect(lambda error, w=worker: self._on_fetch_failed(w, error))
        self._worker = worker
        self._set_busy(True)
        QThreadPool.globalInstance().start(worker)

    def _on_fetched(self, worker: RequestWorker, response: ApiResponse) -> None:
        if worker is not self._worker:
            return
        self._worker = None
        self._set_busy(False)
        if response.status_code >= 400:
            self._show_error(tr("The server answered {status}. Check that springdoc-openapi is enabled and the URL "
                                "is right.", status=response.status_text))
            return
        self.load_text(response.text)

    def _on_fetch_failed(self, worker: RequestWorker, error: RequestError) -> None:
        if worker is not self._worker:
            return
        self._worker = None
        self._set_busy(False)
        self._show_error(f"{error.title}: {error.message}")

    def _choose_file(self) -> None:
        start = str(self._start_dir) if self._start_dir else ""
        chosen, _ = QFileDialog.getOpenFileName(self, tr("Open OpenAPI spec"), start,
                                                tr("OpenAPI JSON (*.json);;All files (*)"))
        if not chosen:
            return
        try:
            text = Path(chosen).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
            self._show_error(tr("Could not read {path}: {error}", path=chosen, error=reason))
            return
        self.load_text(text)

    def load_text(self, text: str) -> None:
        try:
            result = parse_openapi(text)
        except OpenApiError as exc:
            self._show_error(str(exc))
            return
        result.mark_existing(self._collections)
        self._result = result
        self.error.hide()
        self._populate(result)

    def _set_busy(self, busy: bool) -> None:
        self.load_button.setEnabled(not busy)
        self.file_button.setEnabled(not busy)
        self.url.setReadOnly(busy)
        if busy:
            self.error.hide()
            self.status.setText(tr("Loading spec…"))

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.status.setText("")

    # -- preview --------------------------------------------------------------------

    def _populate(self, result: OpenApiImport) -> None:
        theme = current_theme()
        existing_collections = {c.name.casefold() for c in self._collections}
        self.tree.blockSignals(True)
        self.tree.clear()
        path_font = monospace_font(12)
        method_font = monospace_font(12)
        method_font.setBold(True)
        for name, endpoints in result.collections().items():
            marker = tr("existing collection") if name.casefold() in existing_collections else tr("new collection")
            parent = QTreeWidgetItem([f"{name}  ({marker})"])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            self.tree.addTopLevelItem(parent)
            parent.setFirstColumnSpanned(True)
            for endpoint in endpoints:
                request = endpoint.request
                child = QTreeWidgetItem([request.method.value, endpoint.path, request.name])
                child.setData(0, _ENDPOINT_ROLE, endpoint)
                child.setFont(0, method_font)
                child.setFont(1, path_font)
                if endpoint.exists:
                    child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    child.setText(2, tr("already in the project"))
                    for column in range(3):
                        child.setForeground(column, QColor(theme.text_faint))
                else:
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Checked)
                    child.setForeground(0, QColor(theme.method_color(request.method.value)))
                parent.addChild(child)
            if all(e.exists for e in endpoints):
                parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                parent.setForeground(0, QColor(theme.text_faint))
            else:
                parent.setCheckState(0, Qt.CheckState.Checked)
        self.tree.expandAll()
        # Spanned collection rows do not count when sizing, so fit the longest method by hand.
        method_width = QFontMetrics(method_font).horizontalAdvance("OPTIONS")
        # Endpoints sit one level deep, after the expand arrow column and the checkbox.
        self.tree.setColumnWidth(0, 2 * self.tree.indentation() + method_width + 40)
        self.tree.resizeColumnToContents(1)
        self.tree.blockSignals(False)
        if self.tree.isHidden():
            self.tree.show()
            self.resize(self.width(), max(self.height(), 560))

        new = sum(1 for e in result.endpoints if not e.exists)
        title = f"{result.title} {result.version}".strip() or tr("Spec")
        self.status.setText(tr("{title}: {total}, {new} new.", title=title,
                               total=trn("{n} endpoint", "{n} endpoints", len(result.endpoints)),
                               new=new))
        self.notes.setText("\n".join(f"•  {note}" for note in result.notes))
        self.notes.setVisible(bool(result.notes))
        self._update_selection()

    def selected_endpoints(self) -> list[ImportedEndpoint]:
        selected = []
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                endpoint = child.data(0, _ENDPOINT_ROLE)
                if not endpoint.exists and child.checkState(0) == Qt.CheckState.Checked:
                    selected.append(endpoint)
        return selected

    def _update_selection(self) -> None:
        count = len(self.selected_endpoints())
        self.ok_button.setEnabled(count > 0)
        self.ok_button.setText(trn("Import {n} request", "Import {n} requests", count) if count else tr("Import"))

    def validate(self) -> bool:
        # Enter in the URL field means "load", never "import what was loaded before".
        return not self.url.hasFocus() and bool(self.selected_endpoints())

    def done(self, result: int) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        super().done(result)

    @staticmethod
    def ask(parent: QWidget | None, http: HttpClientService, context: VariableContext,
            collections: list[Collection], start_dir: Path | None = None) -> list[ImportedEndpoint] | None:
        dialog = OpenApiImportDialog(parent, http, context, collections, start_dir)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_endpoints()
        return None
