from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QStackedWidget, QVBoxLayout, QWidget

from app.i18n import tr
from app.models.api_request import BodyType, RequestBody
from app.services.json_service import format_json, validate_json
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import Debouncer, button, hbox, label, vbox
from app.ui.widgets.code_editor import CodeEditor
from app.ui.widgets.json_highlighter import JsonHighlighter


class BodyEditor(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self.type_combo = QComboBox()
        self.type_combo.setProperty("variant", "compact")
        for body_type in BodyType:
            self.type_combo.addItem(body_type.label, body_type)
        self.type_combo.setFixedWidth(96)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.format_button = button(tr("Format"), "ghost", icon_name="braces", on_click=self.format)
        self.format_button.setToolTip(tr("Format JSON (Ctrl+Shift+F)"))

        self.editor = CodeEditor()
        self.editor.setPlaceholderText('{\n  "name": "value"\n}')
        self.highlighter = JsonHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._on_text_changed)

        self._validation_icon = QLabel()
        self._validation = label("", "ValidationLabel")
        self._validate_later = Debouncer(250, self._validate, self)

        empty = QWidget()
        empty.setLayout(vbox(None, label(tr("This request has no body"), "EmptyTitle"),
                             label(tr("Select JSON or Text above to send a request body."), "EmptyText"), None,
                             spacing=6))
        for child in empty.findChildren(QLabel):
            child.setAlignment(Qt.AlignmentFlag.AlignCenter)

        editor_page = QWidget()
        editor_page.setLayout(vbox(self.editor, hbox(self._validation_icon, self._validation, None, spacing=6),
                                   spacing=6))
        self.pages = QStackedWidget()
        self.pages.addWidget(empty)
        self.pages.addWidget(editor_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(hbox(label(tr("Content"), "FieldLabel"), None, self.type_combo, self.format_button, spacing=6))
        layout.addWidget(self.pages, 1)

    # -- public ---------------------------------------------------------------------

    def set_body(self, body: RequestBody) -> None:
        self._loading = True
        self.type_combo.setCurrentIndex(list(BodyType).index(body.type))
        self.editor.setPlainText(body.content)
        self._loading = False
        self._apply_type(body.type)
        self._validate()

    def apply_to(self, body: RequestBody) -> None:
        body.type = BodyType(self.type_combo.currentData())
        body.content = self.editor.toPlainText()

    def body_type(self) -> BodyType:
        return BodyType(self.type_combo.currentData())

    def format(self) -> bool:
        if self.body_type() is not BodyType.JSON:
            return False
        try:
            formatted = format_json(self.editor.toPlainText())
        except json.JSONDecodeError:
            self._validate()
            return False
        if formatted != self.editor.toPlainText():
            self.editor.set_text_preserving_undo(formatted)
        return True

    def show_error_line(self, line: int | None) -> None:
        self.editor.set_error_line(line)

    def set_font_size(self, size: int) -> None:
        self.editor.set_font_size(size)

    def refresh_theme(self) -> None:
        self.highlighter.refresh_theme()
        self.format_button.setIcon(icons.icon("braces", current_theme().text_muted))
        self._validate()

    def focus_editor(self) -> None:
        self.editor.setFocus()

    # -- internals ------------------------------------------------------------------

    def _on_type_changed(self) -> None:
        body_type = self.body_type()
        self._apply_type(body_type)
        if not self._loading:
            if body_type is BodyType.JSON and not self.editor.toPlainText().strip():
                self.editor.setPlainText("{\n  \n}")
            self.changed.emit()
            if body_type is not BodyType.NONE:
                self.editor.setFocus()

    def _apply_type(self, body_type: BodyType) -> None:
        self.pages.setCurrentIndex(0 if body_type is BodyType.NONE else 1)
        self.format_button.setVisible(body_type is BodyType.JSON)
        self.highlighter.setDocument(self.editor.document() if body_type is BodyType.JSON else None)
        self._validate()

    def _on_text_changed(self) -> None:
        if self._loading:
            return
        self._validate_later.trigger()
        self.changed.emit()

    def _validate(self) -> None:
        theme = current_theme()
        if self.body_type() is not BodyType.JSON or not self.editor.toPlainText().strip():
            self._validation.setText("")
            self._validation_icon.clear()
            self.editor.set_error_line(None)
            return
        result = validate_json(self.editor.toPlainText())
        color = theme.success if result.valid else theme.danger
        self._validation.setText(result.summary)
        self._validation.setStyleSheet(f"color: {color};")
        self._validation_icon.setPixmap(icons.pixmap("check-circle" if result.valid else "alert-circle", color, 14))
        self.editor.set_error_line(None if result.valid else result.line)
