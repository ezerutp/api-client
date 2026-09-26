from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QWidget

from app.i18n import tr
from app.models.project import Project
from app.repositories.secrets_repository import Secrets
from app.ui.dialogs.base import BaseDialog, ConfirmDialog, TextInputDialog
from app.ui.helpers import hbox, icon_button, label, vbox
from app.ui.widgets.key_value_editor import KeyValueEditor, KvItem
from app.ui.widgets.top_bar import dot_icon, environment_color
from app.utils.slug import slugify

GLOBALS = "\x00globals"


@dataclass
class EnvironmentsResult:
    global_variables: dict[str, str]
    global_secrets: dict[str, str]
    environments: dict[str, tuple[dict[str, str], dict[str, str]]]


class EnvironmentsDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, project: Project, secrets: Secrets, current: str | None,
                 create_new: bool = False) -> None:
        super().__init__(parent, tr("Environments"), width=820)
        self.setMinimumHeight(500)
        self._data: dict[str, list[KvItem]] = {}
        self._current_key: str | None = None

        globals_items = [KvItem("base_url", project.base_url)] if project.base_url else []
        globals_items += [KvItem(k, v) for k, v in project.variables.items()]
        globals_items += [KvItem(k, v, secret=True) for k, v in secrets.globals.items()]
        self._data[GLOBALS] = globals_items
        for name, env in project.environments.items():
            items = [KvItem(k, v) for k, v in env.variables.items()]
            items += [KvItem(k, v, secret=True) for k, v in secrets.for_environment(name).items()]
            self._data[name] = items

        self.list = QListWidget()
        self.list.setFixedWidth(200)
        self.list.currentItemChanged.connect(self._on_selection_changed)
        self.list.itemDoubleClicked.connect(lambda _: self._rename())
        add = icon_button("plus", tr("Add environment"), size=14, on_click=self._add)
        self._rename_button = icon_button("pencil", tr("Rename"), size=14, on_click=self._rename)
        self._duplicate_button = icon_button("copy", tr("Duplicate"), size=14, on_click=self._duplicate)
        self._delete_button = icon_button("trash", tr("Delete"), size=14, on_click=self._delete)
        self._rename_button.setToolTip(tr("Rename environment"))

        self.env_title = label("", "EmptyTitle")
        self.env_hint = label("", "Hint", wrap=True)
        self.editor = KeyValueEditor(key_placeholder=tr("Variable"), value_placeholder=tr("Value"), secret_column=True)

        left = vbox(label(tr("ENVIRONMENTS"), "SectionLabel"), self.list,
                    hbox(add, self._duplicate_button, self._rename_button, None, self._delete_button, spacing=2),
                    spacing=6)
        right = vbox(self.env_title, self.env_hint, 6, self.editor, spacing=4)
        self.content.addLayout(hbox(left, 10, right, spacing=10), 1)
        self.content.addWidget(label(
            tr("Lock a variable to store it in api-client/.secrets.json, which is git-ignored and never shared. "
               "Environment values override globals."), "Hint", wrap=True))
        self.ok_button.setText(tr("Save"))
        self._populate(current)
        if create_new:
            self._add()

    # -- list management ------------------------------------------------------------

    def _populate(self, select: str | None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        globals_item = QListWidgetItem(tr("Globals"))
        globals_item.setData(Qt.ItemDataRole.UserRole, GLOBALS)
        self.list.addItem(globals_item)
        for name in self._data:
            if name == GLOBALS:
                continue
            item = QListWidgetItem(dot_icon(environment_color(name)), name[:1].upper() + name[1:])
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(item)
        self.list.blockSignals(False)
        target = select if select in self._data else GLOBALS
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == target:
                self.list.setCurrentRow(row)
                break

    def _store_current(self) -> None:
        if self._current_key is not None and self._current_key in self._data:
            self._data[self._current_key] = self.editor.items()

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        self._store_current()
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        self._current_key = key
        is_globals = key == GLOBALS
        self.env_title.setText(tr("Globals") if is_globals else current.text())
        self.env_hint.setText(tr("Shared by every environment.") if is_globals else
                              tr("Active when “{env}” is selected in the top bar.", env=current.text()))
        self.editor.set_items(self._data.get(key, []))
        for widget in (self._rename_button, self._delete_button, self._duplicate_button):
            widget.setEnabled(not is_globals)

    def _ask_name(self, title: str, value: str = "") -> str | None:
        name = TextInputDialog.ask(self, title, tr("Environment name"), value, tr("Save"))
        if not name:
            return None
        slug = slugify(name, fallback="environment")
        base, counter = slug, 2
        while slug in self._data and slug != value:
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def _add(self) -> None:
        name = self._ask_name(tr("New environment"))
        if name:
            self._store_current()
            self._data[name] = [KvItem("base_url", "")]
            self._populate(name)
            self.editor.focus_first()

    def _duplicate(self) -> None:
        if self._current_key in (None, GLOBALS):
            return
        self._store_current()
        name = self._ask_name(tr("Duplicate environment"), f"{self._current_key}-copy")
        if name:
            self._data[name] = [KvItem(i.key, i.value, i.enabled, i.secret) for i in self._data[self._current_key]]
            self._populate(name)

    def _rename(self) -> None:
        old = self._current_key
        if old in (None, GLOBALS):
            return
        self._store_current()
        new = self._ask_name(tr("Rename environment"), old)
        if new and new != old:
            self._data = {(new if k == old else k): v for k, v in self._data.items()}
            self._current_key = None
            self._populate(new)

    def _delete(self) -> None:
        key = self._current_key
        if key in (None, GLOBALS):
            return
        if ConfirmDialog.ask(self, tr("Delete environment?"), tr("“{env}” and its variables (including secrets) will be removed when you save.", env=key)):
            del self._data[key]
            self._current_key = None
            self._populate(GLOBALS)

    # -- result ---------------------------------------------------------------------

    def result_value(self) -> EnvironmentsResult:
        self._store_current()

        def split(items: list[KvItem]) -> tuple[dict[str, str], dict[str, str]]:
            plain, secret = {}, {}
            for item in items:
                if item.key.strip() and item.enabled:
                    (secret if item.secret else plain)[item.key.strip()] = item.value
            return plain, secret

        global_vars, global_secrets = split(self._data.get(GLOBALS, []))
        envs = {name: split(items) for name, items in self._data.items() if name != GLOBALS}
        return EnvironmentsResult(global_vars, global_secrets, envs)

    @staticmethod
    def ask(parent: QWidget | None, project: Project, secrets: Secrets, current: str | None,
            create_new: bool = False) -> EnvironmentsResult | None:
        dialog = EnvironmentsDialog(parent, project, secrets, current, create_new)
        return dialog.result_value() if dialog.exec() == QDialog.DialogCode.Accepted else None
