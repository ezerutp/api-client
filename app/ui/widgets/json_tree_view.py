"""Read-only tree view of a JSON document ("Object view" next to the body editor)."""

from __future__ import annotations

import json
import re
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHeaderView, QMenu, QStackedWidget, QTreeWidget, QTreeWidgetItem, QWidget

from app.i18n import tr, trn
from app.services.json_service import JsonVariable, parse_json
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import apply_icon, hbox, icon_button, label, monospace_font, vbox

#: Building a QTreeWidget item per node gets slow past this; the rest is summarised.
MAX_NODES = 5000
_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_VALUE = Qt.ItemDataRole.UserRole + 1
_VAR_MARK = "@@api-client-var@@"
_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")

Path = tuple[str | int, ...]


def json_kind(value: Any) -> str:
    if isinstance(value, JsonVariable):
        return "variable"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def format_path(path: Path) -> str:
    """``("carrera", "id")`` -> ``carrera.id``; ``("items", 0, "a b")`` -> ``items[0]["a b"]``."""
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        elif _IDENTIFIER.match(part):
            text += f".{part}" if text else part
        else:
            text += f"[{json.dumps(part, ensure_ascii=False)}]"
    return text


def summarize(value: Any) -> str:
    if isinstance(value, dict):
        return "{ " + trn("{n} field", "{n} fields", len(value)) + " }"
    if isinstance(value, list):
        return "[ " + trn("{n} item", "{n} items", len(value)) + " ]"
    if isinstance(value, JsonVariable):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def to_json(value: Any) -> str:
    """Copyable text; bare variables stay unquoted, as the user wrote them."""
    if isinstance(value, str):
        return str(value)

    def mark(obj: Any) -> Any:
        if isinstance(obj, JsonVariable):
            return f"{_VAR_MARK}{obj}{_VAR_MARK}"
        if isinstance(obj, dict):
            return {k: mark(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [mark(v) for v in obj]
        return obj

    text = json.dumps(mark(value), indent=2, ensure_ascii=False)
    return re.sub(f'"{_VAR_MARK}(.*?){_VAR_MARK}"', r"\1", text)


class JsonTreeView(QFrame):
    """Shows the last valid document; while the editor text is invalid it keeps it and says so."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObjectView")
        self._value: Any = None
        self._has_value = False
        self._collapsed: set[Path] = set()
        self._badges: dict[str, QIcon] = {}

        self.expand_button = icon_button("chevrons-down-up", tr("Collapse all"), on_click=self.toggle_expand_all, size=14)
        self.title = label(tr("Object"), "ObjectViewTitle")
        self.copy_button = icon_button("copy", tr("Copy value as JSON"), on_click=self.copy_selected, size=14)
        header = QWidget()
        header.setObjectName("ObjectViewHeader")
        header.setLayout(hbox(self.expand_button, self.title, None, self.copy_button, spacing=6, margins=(6, 4, 6, 4)))

        self.tree = QTreeWidget()
        self.tree.setObjectName("ObjectTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_menu)
        self.tree.itemCollapsed.connect(lambda item: self._collapsed.add(item.data(0, _ROLE_PATH)))
        self.tree.itemExpanded.connect(lambda item: self._collapsed.discard(item.data(0, _ROLE_PATH)))

        self.message = label("", "ObjectViewMessage", wrap=True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.tree)
        placeholder = QWidget()
        placeholder.setLayout(vbox(None, self.message, None, margins=(12, 12, 12, 12)))
        self.pages.addWidget(placeholder)

        self.status = label("", "ObjectViewStatus", wrap=True)
        self.status.hide()

        self.setLayout(vbox(header, self.status, self.pages, spacing=0))
        self.set_text("")

    # -- public ---------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        if not text.strip():
            self._has_value = False
            self._value = None
            self._show_message(tr("Nothing to show yet"))
            return
        try:
            value = parse_json(text)
        except ValueError:
            if self._has_value:
                self._set_status(tr("Invalid JSON — showing the last valid version"))
            else:
                self._show_message(tr("Write valid JSON to see its structure"))
            return
        self._set_status("")
        self._value, self._has_value = value, True
        self._rebuild()

    def value(self) -> Any:
        return self._value

    def refresh_theme(self) -> None:
        self._badges.clear()
        for button in (self.expand_button, self.copy_button):
            apply_icon(button)
        self.status.setStyleSheet(f"color: {current_theme().warning};")
        if self._has_value:
            self._rebuild()

    def toggle_expand_all(self) -> None:
        if self._any_expanded():
            self.tree.collapseAll()
        else:
            self.tree.expandAll()
        self._update_expand_button()

    def copy_selected(self) -> None:
        item = self.tree.currentItem()
        value = item.data(0, _ROLE_VALUE) if item is not None and item.isSelected() else self._value
        if self._has_value:
            QGuiApplication.clipboard().setText(to_json(value))

    # -- building -------------------------------------------------------------------

    def _rebuild(self) -> None:
        value = self._value
        kind = json_kind(value)
        self.title.setText({"object": tr("Object"), "array": tr("Array")}.get(kind, tr("Value")))
        scroll = self.tree.verticalScrollBar().value()
        selected = self.tree.currentItem().data(0, _ROLE_PATH) if self.tree.currentItem() else None
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        self.tree.clear()
        budget = [MAX_NODES]
        if kind in ("object", "array"):
            self._add_children(self.tree.invisibleRootItem(), value, (), budget)
        else:
            self._add_node(self.tree.invisibleRootItem(), tr("(value)"), value, (), budget)
        self._restore_expansion(self.tree.invisibleRootItem())
        if selected is not None:
            self._select_path(self.tree.invisibleRootItem(), selected)
        self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(0)
        self.tree.setColumnWidth(0, min(self.tree.columnWidth(0) + 12, 260))
        self.tree.setUpdatesEnabled(True)
        self.tree.verticalScrollBar().setValue(scroll)
        self.pages.setCurrentIndex(0)
        self._update_expand_button()

    def _add_children(self, parent: QTreeWidgetItem, value: Any, path: Path, budget: list[int]) -> None:
        entries = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in entries:
            if budget[0] <= 0:
                more = QTreeWidgetItem(parent, ["…", tr("(too large to show everything)")])
                more.setForeground(1, QColor(current_theme().text_faint))
                return
            self._add_node(parent, f"[{key}]" if isinstance(key, int) else key, child, (*path, key), budget)

    def _add_node(self, parent: QTreeWidgetItem, key: str, value: Any, path: Path, budget: list[int]) -> None:
        budget[0] -= 1
        theme = current_theme()
        kind = json_kind(value)
        item = QTreeWidgetItem(parent, [key, summarize(value)])
        item.setData(0, _ROLE_PATH, path)
        item.setData(0, _ROLE_VALUE, value)
        item.setIcon(0, self._badge(kind))
        item.setToolTip(0, format_path(path) or key)
        color = {
            "string": theme.syntax_string, "number": theme.syntax_number, "boolean": theme.syntax_keyword,
            "null": theme.syntax_keyword, "variable": theme.syntax_variable,
        }.get(kind, theme.text_faint)
        item.setForeground(1, QColor(color))
        if kind in ("object", "array"):
            self._add_children(item, value, path, budget)
        else:
            item.setFont(1, self._value_font())
            item.setToolTip(1, summarize(value))

    def _restore_expansion(self, parent: QTreeWidgetItem) -> None:
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.childCount():
                child.setExpanded(child.data(0, _ROLE_PATH) not in self._collapsed)
                self._restore_expansion(child)

    def _select_path(self, parent: QTreeWidgetItem, path: Path) -> bool:
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.data(0, _ROLE_PATH) == path:
                self.tree.setCurrentItem(child)
                return True
            if self._select_path(child, path):
                return True
        return False

    def _value_font(self) -> QFont:
        return monospace_font(max(self.font().pixelSize(), 12))

    def _badge(self, kind: str) -> QIcon:
        if kind not in self._badges:
            self._badges[kind] = QIcon(_badge_pixmap(kind))
        return self._badges[kind]

    # -- misc -----------------------------------------------------------------------

    def _show_message(self, text: str) -> None:
        self._set_status("")
        self.tree.clear()
        self.title.setText(tr("Object"))
        self.message.setText(text)
        self.pages.setCurrentIndex(1)

    def _set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def _any_expanded(self) -> bool:
        root = self.tree.invisibleRootItem()
        return any(root.child(i).isExpanded() for i in range(root.childCount()))

    def _update_expand_button(self) -> None:
        expanded = self._any_expanded()
        self.expand_button.setProperty("icon_name", "chevrons-down-up" if expanded else "chevrons-up-down")
        self.expand_button.setToolTip(tr("Collapse all") if expanded else tr("Expand all"))
        apply_icon(self.expand_button)

    def _show_menu(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        if item is None or item.data(0, _ROLE_PATH) is None:
            return
        path, value = item.data(0, _ROLE_PATH), item.data(0, _ROLE_VALUE)
        clipboard = QGuiApplication.clipboard()
        menu = QMenu(self)
        menu.addAction(tr("Copy value"), lambda: clipboard.setText(to_json(value)))
        if path:
            menu.addAction(tr("Copy key"), lambda: clipboard.setText(str(path[-1])))
            menu.addAction(tr("Copy path"), lambda: clipboard.setText(format_path(path)))
        menu.exec(self.tree.viewport().mapToGlobal(pos))


def _badge_pixmap(kind: str, size: int = 18) -> QPixmap:
    """Small rounded square with a glyph telling the value type (like the sidebar method tags)."""
    theme = current_theme()
    color = QColor({
        "string": theme.syntax_keyword, "number": theme.syntax_number, "boolean": theme.warning,
        "null": theme.text_faint, "variable": theme.syntax_variable,
    }.get(kind, theme.accent))
    app = QGuiApplication.instance()
    ratio = max(app.devicePixelRatio() if app is not None else 1.0, 2.0)  # type: ignore[union-attr]
    image = QPixmap(int(size * ratio), int(size * ratio))
    image.fill(Qt.GlobalColor.transparent)
    image.setDevicePixelRatio(ratio)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill = QColor(color)
    fill.setAlpha(60 if theme.is_dark else 40)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    rect = QRectF(0, 0, size, size)
    painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
    if kind in ("object", "array"):
        glyph = icons.pixmap("box" if kind == "object" else "list", color.name(), size - 6)
        painter.drawPixmap(3, 3, glyph)
    else:
        font = QFont()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        glyph = {"string": "A", "number": "#", "boolean": "B", "null": "Ø", "variable": "$"}[kind]
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return image
