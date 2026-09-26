from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QWidget

from app.models.api_request import HttpMethod
from app.models.collection import Collection
from app.themes.manager import current_theme
from app.ui.dialogs.base import BaseDialog
from app.ui.helpers import hbox, set_prop

_NEW_COLLECTION = "__new__"


@dataclass
class NewRequestResult:
    name: str
    method: HttpMethod
    collection_id: str | None      # None -> create ``new_collection_name``
    new_collection_name: str
    url: str


class NewRequestDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, collections: list[Collection], selected: str | None) -> None:
        super().__init__(parent, "New Request", width=460)
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
        self.collection.addItem("+ New collection…", _NEW_COLLECTION)
        if selected and selected in self._collections:
            self.collection.setCurrentIndex(self.collection.findData(selected))
        self.collection.currentIndexChanged.connect(self._on_collection_changed)
        self.new_collection = QLineEdit("General" if not collections else "")
        self.new_collection.setPlaceholderText("Collection name, e.g. Productos")
        self.url = QLineEdit()
        self.url.textEdited.connect(self._on_url_edited)

        self.add_field("Name", self.name)
        self.add_field("Method and collection", layout=hbox(self.method, self.collection, spacing=8))
        self._new_collection_caption_index = self.content.count()
        self.add_field("New collection name", self.new_collection)
        self.add_field("URL", self.url, hint="Use {path} for path variables, e.g. {{base_url}}/api/productos/{id}")
        self.ok_button.setText("Create")
        self._on_collection_changed()
        self._update_method_color()
        self.name.setFocus()

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
    def ask(parent: QWidget | None, collections: list[Collection], selected: str | None) -> NewRequestResult | None:
        dialog = NewRequestDialog(parent, collections, selected)
        return dialog.result_value() if dialog.exec() == QDialog.DialogCode.Accepted else None


class CollectionDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, collection: Collection | None) -> None:
        super().__init__(parent, "Edit Collection" if collection else "New Collection", width=440)
        self.name = QLineEdit(collection.name if collection else "")
        self.name.setPlaceholderText("Productos")
        self.base_path = QLineEdit(collection.base_path if collection else "")
        self.base_path.setPlaceholderText("/api/productos")
        self.add_field("Name", self.name)
        self.add_field("Base path (optional)", self.base_path,
                       hint="Mirrors @RequestMapping on the controller. New requests start with "
                            "{{base_url}} + this path.")
        self.ok_button.setText("Save" if collection else "Create")
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
