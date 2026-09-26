from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QLineEdit, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from app.i18n import tr
from app.models.auth import Authentication, AuthType
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import hbox, label, vbox


class AuthEditor(QWidget):
    """Contextual auth form: only the fields of the selected type are shown."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self.type_combo = QComboBox()
        for auth_type in AuthType:
            self.type_combo.addItem(auth_type.label, auth_type)
        self.type_combo.setFixedWidth(180)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.token = QLineEdit()
        self.token.setPlaceholderText("{{token}}")
        self.username = QLineEdit()
        self.username.setPlaceholderText(tr("Username or {{username}}"))
        self.password = QLineEdit()
        self.password.setPlaceholderText(tr("Password or {{password}}"))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self._reveal = QToolButton()
        self._reveal.setCheckable(True)
        self._reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reveal.setToolTip(tr("Show password"))
        self._reveal.toggled.connect(self._toggle_password)
        for field in (self.token, self.username, self.password):
            field.textEdited.connect(self._emit)

        self.pages = QStackedWidget()
        none_page = QWidget()
        none_page.setLayout(vbox(
            label(tr("This request does not send authentication."), "Muted"),
            label(tr("Choose Bearer Token or Basic Auth above to add an Authorization header."), "Hint", wrap=True),
            None, spacing=4,
        ))
        bearer_page = QWidget()
        bearer_page.setLayout(vbox(
            label(tr("Token"), "FieldLabel"), self.token,
            label(tr("Sent as  Authorization: Bearer <token>.  Keep real tokens in .secrets.json and "
                     "reference them as {{token}}."), "Hint", wrap=True),
            None, spacing=6,
        ))
        basic_page = QWidget()
        basic_page.setLayout(vbox(
            label(tr("Username"), "FieldLabel"), self.username, 4,
            label(tr("Password"), "FieldLabel"), hbox(self.password, self._reveal, spacing=4),
            label(tr("Sent as  Authorization: Basic base64(username:password)."), "Hint", wrap=True),
            None, spacing=6,
        ))
        for page in (none_page, bearer_page, basic_page):
            self.pages.addWidget(page)

        form = QWidget()
        form.setMaximumWidth(560)
        form.setLayout(vbox(hbox(label(tr("Type"), "FieldLabel"), self.type_combo, None, spacing=12), 8, self.pages, spacing=4))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.addWidget(form)
        self.refresh_theme()

    def set_auth(self, auth: Authentication) -> None:
        self._loading = True
        self.type_combo.setCurrentIndex(list(AuthType).index(auth.type))
        self.pages.setCurrentIndex(list(AuthType).index(auth.type))
        self.token.setText(auth.token)
        self.username.setText(auth.username)
        self.password.setText(auth.password)
        self._loading = False

    def apply_to(self, auth: Authentication) -> None:
        auth.type = AuthType(self.type_combo.currentData())
        auth.token = self.token.text()
        auth.username = self.username.text()
        auth.password = self.password.text()

    def refresh_theme(self) -> None:
        self._toggle_password(self._reveal.isChecked())

    def _toggle_password(self, visible: bool) -> None:
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self._reveal.setIcon(icons.icon("eye-off" if visible else "eye", current_theme().text_muted))

    def _on_type_changed(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if not self._loading:
            focus = {AuthType.BEARER: self.token, AuthType.BASIC: self.username}.get(AuthType(self.type_combo.currentData()))
            if focus is not None:
                focus.setFocus()
        self._emit()

    def _emit(self) -> None:
        if not self._loading:
            self.changed.emit()
