"""Lightweight enabled/key/value rows (params, headers, path variables, env variables).

Not a spreadsheet: each row is a pair of borderless fields. A new empty row is
appended automatically once the last one is filled, and Tab walks key → value
→ next key.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import apply_icon, icon_button

COMMON_HEADERS = [
    "Accept", "Accept-Encoding", "Accept-Language", "Authorization", "Cache-Control", "Connection",
    "Content-Type", "Cookie", "If-None-Match", "Origin", "Referer", "User-Agent", "X-Api-Key",
    "X-Correlation-Id", "X-Request-Id", "X-Requested-With",
]
COMMON_HEADER_VALUES = [
    "application/json", "application/xml", "text/plain", "application/x-www-form-urlencoded",
    "multipart/form-data", "*/*", "no-cache", "Bearer {{token}}", "gzip, deflate",
]


@dataclass
class KvItem:
    key: str
    value: str
    enabled: bool = True
    secret: bool = False


class _Row(QWidget):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, editor: KeyValueEditor, item: KvItem | None) -> None:
        super().__init__()
        self.setObjectName("KvRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._editor = editor
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.check = QCheckBox()
        self.check.setChecked(True if item is None else item.enabled)
        self.check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.check.setToolTip(tr("Enable / disable"))
        self.key = QLineEdit(item.key if item else "")
        self.value = QLineEdit(item.value if item else "")
        for field, placeholder in ((self.key, editor.key_placeholder), (self.value, editor.value_placeholder)):
            field.setProperty("cell", True)
            field.setPlaceholderText(placeholder)
            field.textEdited.connect(self._on_edit)
        self.key.setReadOnly(editor.fixed_keys)
        if editor.fixed_keys:
            self.key.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if editor.key_completions:
            self._attach_completer(self.key, editor.key_completions)
        if editor.value_completions:
            self._attach_completer(self.value, editor.value_completions)

        self.secret = QToolButton()
        self.secret.setCheckable(True)
        self.secret.setChecked(bool(item and item.secret))
        self.secret.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.secret.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secret.setToolTip(tr("Secret: stored in .secrets.json (not committed)"))
        self.secret.setVisible(editor.secret_column)
        self.secret.toggled.connect(self._on_secret_toggled)
        self.value.installEventFilter(self)

        self.delete = icon_button("trash", tr("Remove"), size=14, on_click=lambda: self.remove_requested.emit(self))
        self.delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.delete.setVisible(not editor.fixed_keys)

        for widget in (self.check, self.delete, self.secret):
            policy = widget.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(policy)
        if not editor.secret_column:
            self.secret.setFixedWidth(0)
        self.check.toggled.connect(lambda _: self.changed.emit())
        layout.addWidget(self.check)
        layout.addWidget(self.key, 2)
        layout.addWidget(self.value, 3)
        layout.addWidget(self.secret)
        layout.addWidget(self.delete)
        self._refresh_secret()
        self.refresh_placeholder_state()

    def _attach_completer(self, field: QLineEdit, words: list[str]) -> None:
        completer = QCompleter(QStringListModel(words, field), field)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.popup().setObjectName("CompleterPopup")
        field.setCompleter(completer)

    def item(self) -> KvItem:
        return KvItem(self.key.text(), self.value.text(), self.check.isChecked(), self.secret.isChecked())

    @property
    def is_blank(self) -> bool:
        return not self.key.text() and not self.value.text()

    def refresh_placeholder_state(self) -> None:
        """The trailing "new row" shows no checkbox/delete button until something is typed."""
        blank = self.is_blank and not self._editor.fixed_keys
        self.check.setVisible(not blank)
        self.delete.setVisible(not blank and not self._editor.fixed_keys)
        self.secret.setVisible(self._editor.secret_column and not blank)

    def _on_edit(self) -> None:
        self.refresh_placeholder_state()
        self.changed.emit()

    def _on_secret_toggled(self) -> None:
        self._refresh_secret()
        self.changed.emit()

    def _refresh_secret(self) -> None:
        theme = current_theme()
        secret = self.secret.isChecked()
        self.secret.setIcon(icons.icon("lock" if secret else "unlock", theme.warning if secret else theme.text_faint, 14))
        masked = secret and not self.value.hasFocus()
        self.value.setEchoMode(QLineEdit.EchoMode.Password if masked else QLineEdit.EchoMode.Normal)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.value and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self._refresh_secret()
        return False

    def refresh_theme(self) -> None:
        apply_icon(self.delete)
        self._refresh_secret()


class KeyValueEditor(QWidget):
    changed = Signal()

    def __init__(
        self,
        *,
        key_placeholder: str = tr("Key"),
        value_placeholder: str = tr("Value"),
        fixed_keys: bool = False,
        secret_column: bool = False,
        key_completions: list[str] | None = None,
        value_completions: list[str] | None = None,
        scrollable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key_placeholder = key_placeholder
        self.value_placeholder = value_placeholder
        self.fixed_keys = fixed_keys
        self.secret_column = secret_column
        self.key_completions = key_completions
        self.value_completions = value_completions
        self._rows: list[_Row] = []

        header = QWidget()
        header.setObjectName("KvHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 4)
        header_layout.setSpacing(6)
        spacer = QLabel()
        spacer.setFixedWidth(QCheckBox().sizeHint().width())
        header_layout.addWidget(spacer)
        key_label = QLabel(key_placeholder.upper())
        value_label = QLabel(value_placeholder.upper())
        for lbl in (key_label, value_label):
            lbl.setContentsMargins(7, 0, 0, 0)
        header_layout.addWidget(key_label, 2)
        header_layout.addWidget(value_label, 3)
        trailing = QLabel()
        trailing.setFixedWidth((26 if secret_column else 0) + (26 if not fixed_keys else 0))
        header_layout.addWidget(trailing)

        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        if scrollable:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(self._rows_host)
            layout.addWidget(scroll, 1)
        else:
            self._rows_host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            layout.addWidget(self._rows_host)
        self._ensure_trailing_row()

    # -- public API -----------------------------------------------------------------

    def set_items(self, items: list[KvItem]) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for item in items:
            self._add_row(item)
        self._ensure_trailing_row()

    def items(self) -> list[KvItem]:
        return [row.item() for row in self._rows if not row.is_blank]

    def active_count(self) -> int:
        return sum(1 for item in self.items() if item.enabled and item.key.strip())

    def focus_first(self) -> None:
        if self._rows:
            target = self._rows[0].value if self.fixed_keys else self._rows[0].key
            target.setFocus()

    def refresh_theme(self) -> None:
        for row in self._rows:
            row.refresh_theme()

    # -- internals ------------------------------------------------------------------

    def _add_row(self, item: KvItem | None) -> _Row:
        row = _Row(self, item)
        row.changed.connect(lambda r=row: self._on_row_changed(r))
        row.remove_requested.connect(self._remove_row)
        self._rows_layout.insertWidget(len(self._rows), row)
        self._rows.append(row)
        self._update_tab_order()
        return row

    def _ensure_trailing_row(self) -> None:
        if self.fixed_keys:
            return
        if not self._rows or not self._rows[-1].is_blank:
            self._add_row(None)

    def _on_row_changed(self, row: _Row) -> None:
        if row is self._rows[-1] and not row.is_blank:
            self._ensure_trailing_row()
        self.changed.emit()

    def _remove_row(self, row: _Row) -> None:
        index = self._rows.index(row)
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._ensure_trailing_row()
        self._update_tab_order()
        if self._rows:
            neighbour = self._rows[min(index, len(self._rows) - 1)]
            neighbour.key.setFocus()
        self.changed.emit()

    def _update_tab_order(self) -> None:
        fields: list[QWidget] = []
        for row in self._rows:
            if not self.fixed_keys:
                fields.append(row.key)
            fields.append(row.value)
        for first, second in zip(fields, fields[1:], strict=False):
            QWidget.setTabOrder(first, second)
