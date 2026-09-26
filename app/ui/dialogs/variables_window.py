"""Floating, non-modal window to browse and edit environment variables.

There is no Save button: every edit is emitted at once through ``changed``.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.models.project import Project
from app.repositories.secrets_repository import Secrets
from app.services.variable_service import is_valid_variable_name
from app.themes.manager import ThemeManager, current_theme
from app.ui import icons
from app.ui.dialogs.base import ConfirmDialog, TextInputDialog
from app.ui.helpers import button, hbox, icon_button, label
from app.ui.widgets.toast import Toast
from app.ui.widgets.top_bar import dot_icon, environment_color
from app.utils.slug import slugify

GLOBALS = "\x00globals"
NAME, VALUE, SECRET, ACTIONS = range(4)
_SECRET_ROLE = Qt.ItemDataRole.UserRole + 1
_MASK = "•" * 16


@dataclass
class Variable:
    name: str
    value: str
    secret: bool = False


@dataclass
class EnvironmentsResult:
    global_variables: dict[str, str]
    global_secrets: dict[str, str]
    environments: dict[str, tuple[dict[str, str], dict[str, str]]]


def _display_name(key: str) -> str:
    return tr("Globals") if key == GLOBALS else key[:1].upper() + key[1:]


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(34, 18)

    def paintEvent(self, _event) -> None:
        theme = current_theme()
        rect = QRectF(self.rect())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.accent if self.isChecked() else theme.border_strong))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        knob = rect.height() - 4
        x = rect.width() - knob - 2 if self.isChecked() else 2
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(x, 2, knob, knob))
        painter.end()


class _CellDelegate(QStyledItemDelegate):
    """Masks secret values and edits cells with the borderless key/value field style."""

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        if index.column() == VALUE and index.data(_SECRET_ROLE) and option.text:
            option.text = _MASK

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = QLineEdit(parent)
        editor.setProperty("cell", True)
        return editor


def _centered(widget: QWidget) -> QWidget:
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
    return host


class VariablesWindow(QDialog):
    changed = Signal(object)  # EnvironmentsResult

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Environment variables"))
        self.setModal(False)
        self.setMinimumSize(520, 320)
        self.resize(660, 460)
        self._data: dict[str, list[Variable]] = {GLOBALS: []}
        self._current = GLOBALS
        self._active: str | None = None
        self._loading = False

        self.env_button = QToolButton()
        self.env_button.setObjectName("EnvButton")
        self.env_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.env_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.env_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.env_button.setMinimumWidth(120)
        self._env_menu = QMenu(self.env_button)
        self._env_menu.aboutToShow.connect(self._build_env_menu)
        self.env_button.setMenu(self._env_menu)

        self.search = QLineEdit()
        self.search.setObjectName("SearchField")
        self.search.setPlaceholderText(tr("Search variables…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self._search_icon = QLabel(self.search)
        self._search_icon.move(10, 9)

        self.new_button = button(tr("New variable"), "primary", icon_name="plus", on_click=self.add_variable)
        self.new_button.setAutoDefault(False)

        self.scope_hint = label("", "Hint", wrap=True)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("VariablesTable")
        self.table.setHorizontalHeaderLabels([tr("Name"), tr("Value"), tr("Secret"), tr("Actions")])
        self.table.setItemDelegate(_CellDelegate(self.table))
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(VALUE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(SECRET, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(NAME, 170)
        for column in (SECRET, ACTIONS):
            self.table.horizontalHeaderItem(column).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setColumnWidth(SECRET, 80)
        self.table.setColumnWidth(ACTIONS, 80)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDelegate().closeEditor.connect(lambda *_: QTimer.singleShot(0, self._drop_blank_rows))
        delete_action = QAction(self.table)
        delete_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Delete))
        delete_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        delete_action.triggered.connect(self._delete_selected)
        self.table.addAction(delete_action)

        self.empty_label = label("", "EmptyText")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty_label)

        footer = label(tr("Secret values are stored in api-client/.secrets.json, which is git-ignored and never "
                          "shared. Environment values override globals."), "Hint", wrap=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(label(tr("Environment variables"), "DialogTitle"))
        layout.addLayout(hbox(self.env_button, self.search, self.new_button, spacing=8))
        layout.addWidget(self.scope_hint)
        layout.addWidget(self.stack, 1)
        layout.addWidget(footer)
        self.toast = Toast(self)

        ThemeManager.instance().theme_changed.connect(lambda _: self._refresh_theme())
        self._refresh_theme()

    # -- public API -----------------------------------------------------------------

    def load(self, project: Project, secrets: Secrets, select: str | None = None, active: str | None = None) -> None:
        """Show the project's variables; ``select=None`` keeps the scope currently shown."""
        globals_vars = []
        if project.base_url and "base_url" not in secrets.globals:
            globals_vars.append(Variable("base_url", project.base_url))
        globals_vars += [Variable(k, v) for k, v in project.variables.items()]
        globals_vars += [Variable(k, v, secret=True) for k, v in secrets.globals.items()]
        self._data = {GLOBALS: globals_vars}
        for name, env in project.environments.items():
            self._data[name] = [Variable(k, v) for k, v in env.variables.items()]
            self._data[name] += [Variable(k, v, secret=True) for k, v in secrets.for_environment(name).items()]
        self._active = active
        target = select if select is not None else self._current
        self.select_scope(target if target in self._data else GLOBALS)

    def set_active(self, active: str | None) -> None:
        self._active = active

    def select_scope(self, key: str) -> None:
        self._current = key if key in self._data else GLOBALS
        self.env_button.setText(f" {_display_name(self._current)}")
        self.env_button.setIcon(self._scope_icon(self._current))
        self.scope_hint.setText(tr("Shared by every environment.") if self._current == GLOBALS else
                                tr("Active when “{env}” is selected in the top bar.",
                                   env=_display_name(self._current)))
        self._rebuild()

    @property
    def current_scope(self) -> str:
        return self._current

    def variables(self) -> list[Variable]:
        return self._data[self._current]

    def add_variable(self) -> None:
        self.search.clear()
        self.variables().append(Variable("", ""))
        self._rebuild()
        row = self.table.rowCount() - 1
        self.table.setCurrentCell(row, NAME)
        self.table.editItem(self.table.item(row, NAME))

    def add_environment(self) -> None:
        name = self._ask_env_name(tr("New environment"))
        if name:
            self._data[name] = [Variable("base_url", "")]
            self._emit()
            self.select_scope(name)

    def result_value(self) -> EnvironmentsResult:
        def split(variables: list[Variable]) -> tuple[dict[str, str], dict[str, str]]:
            plain: dict[str, str] = {}
            secret: dict[str, str] = {}
            for var in variables:
                if var.name:
                    (secret if var.secret else plain)[var.name] = var.value
            return plain, secret

        global_vars, global_secrets = split(self._data[GLOBALS])
        envs = {name: split(variables) for name, variables in self._data.items() if name != GLOBALS}
        return EnvironmentsResult(global_vars, global_secrets, envs)

    # -- table ----------------------------------------------------------------------

    def _rebuild(self) -> None:
        self._loading = True
        self.table.setRowCount(0)
        for row, var in enumerate(self.variables()):
            self.table.insertRow(row)
            name = QTableWidgetItem(var.name)
            value = QTableWidgetItem(var.value)
            value.setData(_SECRET_ROLE, var.secret)
            value.setToolTip("" if var.secret else var.value)
            self.table.setItem(row, NAME, name)
            self.table.setItem(row, VALUE, value)
            for column in (SECRET, ACTIONS):
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row, column, item)

            toggle = ToggleSwitch()
            toggle.setChecked(var.secret)
            toggle.setToolTip(tr("Secret: stored in .secrets.json (not committed)"))
            toggle.toggled.connect(lambda checked, v=var: self._set_secret(v, checked))
            self.table.setCellWidget(row, SECRET, _centered(toggle))

            more = icon_button("more", tr("More actions"), size=16)
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            more.setMenu(self._row_menu(more, var))
            self.table.setCellWidget(row, ACTIONS, _centered(more))
        self._loading = False
        self._apply_filter()

    def _row_menu(self, parent: QWidget, var: Variable) -> QMenu:
        menu = QMenu(parent)
        menu.aboutToShow.connect(lambda: self._fill_row_menu(menu, var))
        return menu

    def _fill_row_menu(self, menu: QMenu, var: Variable) -> None:
        # Built on show: the variable may have been renamed since the row was created.
        menu.clear()
        reference = "{{" + var.name + "}}"
        menu.addAction(tr("Edit value"), lambda: self._edit(var, VALUE))
        menu.addAction(tr("Rename"), lambda: self._edit(var, NAME))
        menu.addSeparator()
        menu.addAction(tr("Copy value"), lambda: self._copy(var.value, tr("Value copied to clipboard")))
        menu.addAction(tr("Copy {var}", var=reference), lambda: self._copy(reference, tr("Copied {text}", text=reference)))
        menu.addSeparator()
        # Deferred: deleting rebuilds the table, which owns the button this menu belongs to.
        menu.addAction(tr("Delete"), lambda: QTimer.singleShot(0, lambda: self._delete(var)))

    def _copy(self, text: str, message: str) -> None:
        QApplication.clipboard().setText(text)
        self.toast.show_message(message)

    def _edit(self, var: Variable, column: int) -> None:
        row = self._row_of(var)
        if row is not None:
            self.table.setCurrentCell(row, column)
            self.table.editItem(self.table.item(row, column))

    def _row_of(self, var: Variable) -> int | None:
        for row, candidate in enumerate(self.variables()):
            if candidate is var:
                return row
        return None

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() not in (NAME, VALUE):
            return
        var = self.variables()[item.row()]
        if item.column() == VALUE:
            if item.text() != var.value:
                var.value = item.text()
                item.setToolTip("" if var.secret else var.value)
                self._emit()
            return
        name = item.text().strip()
        if name == var.name:
            return
        error = self._name_error(name, var)
        if error:
            self._set_item_text(item, var.name)
            self.toast.show_message(error, 3200)
            if not var.name:  # a new row: let the user fix the name instead of losing it
                QTimer.singleShot(0, lambda: self._edit(var, NAME))
            return
        was_new = not var.name
        var.name = name
        self._set_item_text(item, name)
        self._emit()
        if was_new:
            QTimer.singleShot(0, lambda: self._edit(var, VALUE))

    def _set_item_text(self, item: QTableWidgetItem, text: str) -> None:
        self._loading = True
        item.setText(text)
        self._loading = False

    def _name_error(self, name: str, var: Variable) -> str | None:
        if not name:
            return tr("Enter a variable name.")
        if not is_valid_variable_name(name):
            return tr("Use letters, numbers, _ . or - (not starting with a number).")
        if any(other.name == name for other in self.variables() if other is not var):
            return tr("{var} already exists in {scope}.", var="{{" + name + "}}", scope=_display_name(self._current))
        return None

    def _drop_blank_rows(self) -> None:
        """A row added with "New" and abandoned without a name is discarded."""
        if self.table.state() == QAbstractItemView.State.EditingState:
            return
        variables = self.variables()
        if any(not v.name for v in variables):
            variables[:] = [v for v in variables if v.name]
            self._rebuild()

    def _set_secret(self, var: Variable, secret: bool) -> None:
        if var.secret == secret:
            return
        var.secret = secret
        row = self._row_of(var)
        if row is not None:
            value = self.table.item(row, VALUE)
            self._loading = True
            value.setData(_SECRET_ROLE, secret)
            value.setToolTip("" if secret else var.value)
            self._loading = False
        if var.name:
            self._emit()

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.variables()):
            self._delete(self.variables()[row])

    def _delete(self, var: Variable) -> None:
        if var.name and not ConfirmDialog.ask(
            self, tr("Delete variable?"),
            tr("{var} will be removed from {scope}.", var="{{" + var.name + "}}", scope=_display_name(self._current)),
        ):
            return
        self.variables().remove(var)
        self._rebuild()
        if var.name:
            self._emit()

    def _apply_filter(self) -> None:
        text = self.search.text().strip().lower()
        visible = 0
        for row, var in enumerate(self.variables()):
            match = not text or not var.name or text in var.name.lower() or (
                not var.secret and text in var.value.lower())
            self.table.setRowHidden(row, not match)
            visible += match
        if visible:
            self.stack.setCurrentWidget(self.table)
        else:
            self.empty_label.setText(tr("No variables match “{text}”.", text=self.search.text().strip()) if text
                                     else tr("No variables yet. Use “New variable” to add one."))
            self.stack.setCurrentWidget(self.empty_label)

    # -- environments ---------------------------------------------------------------

    def _scope_icon(self, key: str):
        theme = current_theme()
        return dot_icon(theme.text_faint if key == GLOBALS else environment_color(key))

    def _build_env_menu(self) -> None:
        menu = self._env_menu
        menu.clear()
        group = QActionGroup(menu)
        for key in self._data:
            text = _display_name(key)
            if key == self._active:
                text = f"{text}  ({tr('active')})"
            action = QAction(self._scope_icon(key), text, menu)
            action.setCheckable(True)
            action.setChecked(key == self._current)
            action.triggered.connect(lambda _=False, k=key: self.select_scope(k))
            group.addAction(action)
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(tr("New environment…"), self.add_environment)
        is_env = self._current != GLOBALS
        for text, handler in ((tr("Rename environment…"), self._rename_environment),
                              (tr("Duplicate environment…"), self._duplicate_environment),
                              (tr("Delete environment…"), self._delete_environment)):
            action = menu.addAction(text, handler)
            action.setEnabled(is_env)

    def _ask_env_name(self, title: str, value: str = "") -> str | None:
        name = TextInputDialog.ask(self, title, tr("Environment name"), value, tr("Save"))
        if not name:
            return None
        slug = slugify(name, fallback="environment")
        base, counter = slug, 2
        while slug in self._data and slug != value:
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def _rename_environment(self) -> None:
        old = self._current
        if old == GLOBALS:
            return
        new = self._ask_env_name(tr("Rename environment"), old)
        if new and new != old:
            self._data = {(new if k == old else k): v for k, v in self._data.items()}
            if self._active == old:
                self._active = new
            self._emit()
            self.select_scope(new)

    def _duplicate_environment(self) -> None:
        source = self._current
        if source == GLOBALS:
            return
        name = self._ask_env_name(tr("Duplicate environment"), f"{source}-copy")
        if name:
            self._data[name] = [Variable(v.name, v.value, v.secret) for v in self._data[source] if v.name]
            self._emit()
            self.select_scope(name)

    def _delete_environment(self) -> None:
        key = self._current
        if key == GLOBALS:
            return
        if ConfirmDialog.ask(self, tr("Delete environment?"),
                             tr("“{env}” and its variables (including secrets) will be deleted.",
                                env=_display_name(key))):
            del self._data[key]
            self._emit()
            self.select_scope(GLOBALS)

    # -- misc -----------------------------------------------------------------------

    def _emit(self) -> None:
        self.changed.emit(self.result_value())

    def _refresh_theme(self) -> None:
        theme = current_theme()
        self._search_icon.setPixmap(icons.pixmap("search", theme.text_faint, 14))
        self.new_button.setIcon(icons.icon("plus", theme.accent_text))
        self.env_button.setIcon(self._scope_icon(self._current))
        self._rebuild()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.reposition()
