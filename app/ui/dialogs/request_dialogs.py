from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QWidget

from app.i18n import tr
from app.models.api_request import ApiRequest, HttpMethod
from app.models.collection import Collection
from app.services.curl_service import CurlImport, CurlParseError, looks_like_curl, parse_curl
from app.themes.manager import current_theme
from app.ui.dialogs.base import BaseDialog
from app.ui.helpers import hbox, label, set_prop
from app.ui.widgets.code_editor import CodeEditor

_NEW_COLLECTION = "__new__"


@dataclass
class NewRequestResult:
    name: str
    method: HttpMethod
    collection_id: str | None      # None -> create ``new_collection_name``
    new_collection_name: str
    url: str


class NewRequestDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, collections: list[Collection], selected: str | None,
                 initial: ApiRequest | None = None) -> None:
        super().__init__(parent, tr("New Request"), width=460)
        self._collections = {c.id: c for c in collections}
        self._url_touched = False
        theme = current_theme()

        self.name = QLineEdit()
        self.name.setPlaceholderText("Crear producto")
        self.method = QComboBox()
        for index, method in enumerate(HttpMethod):
            self.method.addItem(method.value, method)
            self.method.setItemData(index, QColor(theme.method_color(method.value)), Qt.ItemDataRole.ForegroundRole)
        self.method.setFixedWidth(116)
        self.method.currentIndexChanged.connect(self._update_method_color)
        self.collection = QComboBox()
        for collection in collections:
            self.collection.addItem(collection.name, collection.id)
        self.collection.addItem(tr("+ New collection…"), _NEW_COLLECTION)
        if selected and selected in self._collections:
            self.collection.setCurrentIndex(self.collection.findData(selected))
        self.collection.currentIndexChanged.connect(self._on_collection_changed)
        self.new_collection = QLineEdit(tr("General") if not collections else "")
        self.new_collection.setPlaceholderText(tr("Collection name, e.g. Productos"))
        self.url = QLineEdit()
        self.url.textEdited.connect(self._on_url_edited)

        self.add_field(tr("Name"), self.name)
        self.add_field(tr("Method and collection"), layout=hbox(self.method, self.collection, spacing=8))
        self._new_collection_caption_index = self.content.count()
        self.add_field(tr("New collection name"), self.new_collection)
        self.add_field(tr("URL"), self.url, hint=tr("Use {id}-style placeholders for path variables, e.g. {{base_url}}/api/productos/{id}"))
        self.ok_button.setText(tr("Create"))
        if initial is not None:  # e.g. imported from cURL: keep its method and URL
            self.name.setText(initial.name)
            self.method.setCurrentIndex(self.method.findData(initial.method))
            self.url.setText(initial.url)
            self._url_touched = True
        self._on_collection_changed()
        self._update_method_color()
        self.name.setFocus()
        self.name.selectAll()

    def _update_method_color(self) -> None:
        method = HttpMethod(self.method.currentData())
        self.method.setStyleSheet(f"color: {current_theme().method_color(method.value)}; font-weight: 700;")

    def _is_new_collection(self) -> bool:
        return self.collection.currentData() == _NEW_COLLECTION

    def _on_collection_changed(self) -> None:
        is_new = self._is_new_collection()
        for i in range(self._new_collection_caption_index, self._new_collection_caption_index + 2):
            widget = self.content.itemAt(i).widget()
            if widget is not None:
                widget.setVisible(is_new)
        if not self._url_touched:
            collection = self._collections.get(self.collection.currentData())
            self.url.setText("{{base_url}}" + (collection.base_path if collection else ""))
        self.adjustSize()

    def _on_url_edited(self) -> None:
        self._url_touched = True

    def validate(self) -> bool:
        ok = bool(self.name.text().strip())
        set_prop(self.name, "invalid", not ok)
        if self._is_new_collection() and not self.new_collection.text().strip():
            set_prop(self.new_collection, "invalid", True)
            ok = False
        return ok

    def result_value(self) -> NewRequestResult:
        return NewRequestResult(
            name=self.name.text().strip(),
            method=HttpMethod(self.method.currentData()),
            collection_id=None if self._is_new_collection() else self.collection.currentData(),
            new_collection_name=self.new_collection.text().strip(),
            url=self.url.text().strip(),
        )

    @staticmethod
    def ask(parent: QWidget | None, collections: list[Collection], selected: str | None,
            initial: ApiRequest | None = None) -> NewRequestResult | None:
        dialog = NewRequestDialog(parent, collections, selected, initial)
        return dialog.result_value() if dialog.exec() == QDialog.DialogCode.Accepted else None


class CurlImportDialog(BaseDialog):
    """Paste a cURL command; the next step (NewRequestDialog) picks name and collection."""

    def __init__(self, parent: QWidget | None, base_url: str) -> None:
        super().__init__(parent, tr("Import cURL"), width=620)
        self._base_url = base_url
        self._result: CurlImport | None = None
        self.command = CodeEditor()
        self.command.setPlaceholderText("curl 'https://api.example.com/items' -H 'Accept: application/json'")
        self.command.setMinimumHeight(180)
        self.command.set_wrap(True)
        clipboard = QGuiApplication.clipboard().text()
        if looks_like_curl(clipboard):
            self.command.setPlainText(clipboard.strip())
        self.error = label("", "FieldError", wrap=True)
        self.error.hide()
        self.command.textChanged.connect(lambda: (self.error.hide(), set_prop(self.command, "error", False)))
        self.add_field(tr("cURL command"), self.command,
                       hint=tr("Works with “Copy as cURL” from the browser (bash or cmd) and commands from API docs. "
                               "URLs under the active base URL become {{base_url}}."))
        self.content.addWidget(self.error)
        self.ok_button.setText(tr("Continue"))
        self.command.setFocus()

    def validate(self) -> bool:
        try:
            self._result = parse_curl(self.command.toPlainText(), self._base_url)
        except CurlParseError as exc:
            self.error.setText(str(exc))
            self.error.show()
            set_prop(self.command, "error", True)
            return False
        return True

    @staticmethod
    def ask(parent: QWidget | None, base_url: str) -> CurlImport | None:
        dialog = CurlImportDialog(parent, base_url)
        return dialog._result if dialog.exec() == QDialog.DialogCode.Accepted else None


class CollectionDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, collection: Collection | None) -> None:
        super().__init__(parent, tr("Edit Collection") if collection else tr("New Collection"), width=440)
        self.name = QLineEdit(collection.name if collection else "")
        self.name.setPlaceholderText("Productos")
        self.base_path = QLineEdit(collection.base_path if collection else "")
        self.base_path.setPlaceholderText("/api/productos")
        self.add_field(tr("Name"), self.name)
        self.add_field(tr("Base path (optional)"), self.base_path,
                       hint=tr("Mirrors @RequestMapping on the controller. New requests start with "
                               "{{base_url}} + this path."))
        self.ok_button.setText(tr("Save") if collection else tr("Create"))
        self.name.setFocus()
        self.name.selectAll()

    def validate(self) -> bool:
        ok = bool(self.name.text().strip())
        set_prop(self.name, "invalid", not ok)
        return ok

    @staticmethod
    def ask(parent: QWidget | None, collection: Collection | None = None) -> tuple[str, str] | None:
        dialog = CollectionDialog(parent, collection)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.name.text().strip(), dialog.base_path.text().strip()
        return None
