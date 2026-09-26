"""Consistent, compact dialogs (never the platform QMessageBox)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.i18n import tr
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import button, hbox, label, set_prop, vbox


class BaseDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, *, width: int = 440) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        self.title_label = label(title, "DialogTitle")
        self.content = QVBoxLayout()
        self.content.setSpacing(6)
        self.cancel_button = button(tr("Cancel"), on_click=self.reject)
        self.ok_button = button(tr("OK"), "primary", on_click=self._try_accept)
        self.ok_button.setDefault(True)
        self.ok_button.setAutoDefault(True)
        self.cancel_button.setAutoDefault(False)
        self.buttons = hbox(None, self.cancel_button, self.ok_button, spacing=8)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(self.title_label)
        layout.addLayout(self.content)
        layout.addSpacing(4)
        layout.addLayout(self.buttons)

    def add_field(self, caption: str, widget: QWidget | None = None, *, layout=None, hint: str = "") -> None:
        self.content.addWidget(label(caption, "FieldLabel"))
        if layout is not None:
            self.content.addLayout(layout)
        elif widget is not None:
            self.content.addWidget(widget)
        if hint:
            self.content.addWidget(label(hint, "Hint", wrap=True))
        self.content.addSpacing(6)

    def validate(self) -> bool:
        return True

    def _try_accept(self) -> None:
        if self.validate():
            self.accept()


class ConfirmDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, title: str, message: str, confirm_text: str, danger: bool,
                 cancel_text: str | None = None) -> None:
        super().__init__(parent, title, width=400)
        if cancel_text:
            self.cancel_button.setText(cancel_text)
        text = label(message, "DialogMessage", wrap=True)
        self.content.addWidget(text)
        self.ok_button.setText(confirm_text)
        set_prop(self.ok_button, "variant", "danger" if danger else "primary")
        # Destructive actions should not be one Enter away.
        if danger:
            self.ok_button.setDefault(False)
            self.cancel_button.setDefault(True)
            self.cancel_button.setFocus()

    @staticmethod
    def ask(parent: QWidget | None, title: str, message: str, confirm_text: str | None = None,
            danger: bool = True, cancel_text: str | None = None) -> bool:
        dialog = ConfirmDialog(parent, title, message, confirm_text or tr("Delete"), danger, cancel_text)
        return dialog.exec() == QDialog.DialogCode.Accepted


class MessageDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, title: str, message: str, details: Sequence[str] = (),
                 kind: str = "error") -> None:
        super().__init__(parent, title, width=460)
        theme = current_theme()
        color = {"error": theme.danger, "warning": theme.warning}.get(kind, theme.info)
        icon = QLabel()
        icon.setPixmap(icons.pixmap("alert-triangle" if kind == "warning" else "alert-circle", color, 20))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        body = vbox(label(message, "DialogMessage", wrap=True), spacing=6)
        for line in details:
            detail = label(f"•  {line}", "Hint", wrap=True)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body.addWidget(detail)
        self.content.addLayout(hbox(icon, body, spacing=12))
        self.cancel_button.hide()

    @staticmethod
    def show_error(parent: QWidget | None, title: str, message: str, details: Sequence[str] = ()) -> None:
        MessageDialog(parent, title, message, details, "error").exec()

    @staticmethod
    def show_warning(parent: QWidget | None, title: str, message: str, details: Sequence[str] = ()) -> None:
        MessageDialog(parent, title, message, details, "warning").exec()


class TextInputDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, title: str, caption: str, value: str, ok_text: str) -> None:
        super().__init__(parent, title, width=400)
        self.field = QLineEdit(value)
        self.field.selectAll()
        self.add_field(caption, self.field)
        self.ok_button.setText(ok_text)

    def validate(self) -> bool:
        ok = bool(self.field.text().strip())
        set_prop(self.field, "invalid", not ok)
        return ok

    @staticmethod
    def ask(parent: QWidget | None, title: str, caption: str, value: str = "", ok_text: str | None = None) -> str | None:
        dialog = TextInputDialog(parent, title, caption, value, ok_text or tr("Save"))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.field.text().strip()
        return None


class ChoiceDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, title: str, caption: str, options: Sequence[tuple[str, str]],
                 current: str | None, ok_text: str) -> None:
        super().__init__(parent, title, width=400)
        self.combo = QComboBox()
        for key, text in options:
            self.combo.addItem(text, key)
        if current is not None:
            index = self.combo.findData(current)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self.add_field(caption, self.combo)
        self.ok_button.setText(ok_text)

    @staticmethod
    def ask(parent: QWidget | None, title: str, caption: str, options: Sequence[tuple[str, str]],
            current: str | None = None, ok_text: str = tr("OK")) -> str | None:
        dialog = ChoiceDialog(parent, title, caption, options, current, ok_text)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.combo.currentData()
        return None


def field_error_label() -> QLabel:
    error = label("", "FieldError", wrap=True)
    error.hide()
    return error


__all__ = ["BaseDialog", "ChoiceDialog", "ConfirmDialog", "MessageDialog", "TextInputDialog", "field_error_label"]
