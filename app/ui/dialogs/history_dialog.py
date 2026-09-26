from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QLineEdit, QTreeWidget, QTreeWidgetItem, QWidget

from app.i18n import tr
from app.models.history import HistoryEntry
from app.themes.manager import current_theme
from app.ui.dialogs.base import BaseDialog, ConfirmDialog
from app.ui.helpers import button, label
from app.utils.formatting import format_duration, format_size


class HistoryDialog(BaseDialog):
    open_request = Signal(str)

    def __init__(self, parent: QWidget | None, entries: list[HistoryEntry], on_clear: Callable[[], None]) -> None:
        super().__init__(parent, tr("History"), width=860)
        self.setMinimumHeight(480)
        self._on_clear = on_clear
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filter by URL, method, status or request name…"))
        self.filter.textChanged.connect(self._apply_filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("TIME"), tr("METHOD"), tr("URL"), tr("STATUS"), tr("DURATION"), tr("SIZE")])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 130), (1, 76), (3, 150), (4, 84), (5, 76)):
            self.tree.setColumnWidth(column, width)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self._fill(entries)

        self.content.addWidget(self.filter)
        self.content.addWidget(self.tree, 1)
        self.content.addWidget(label(tr("Double-click an entry to open its request. Response bodies are not stored."),
                                     "Hint"))
        self.clear_button = button(tr("Clear history"), "ghost", icon_name="trash", on_click=self._clear)
        self.buttons.insertWidget(0, self.clear_button)
        self.cancel_button.hide()
        self.ok_button.setText(tr("Close"))

    def _fill(self, entries: list[HistoryEntry]) -> None:
        theme = current_theme()
        self.tree.clear()
        for entry in entries:
            try:
                when = datetime.fromisoformat(entry.timestamp).strftime(tr("%b %d  %H:%M:%S"))
            except ValueError:
                when = entry.timestamp
            status = str(entry.status_code) if entry.status_code is not None else (entry.error or tr("Error"))
            item = QTreeWidgetItem([when, entry.method, entry.url, status, format_duration(entry.elapsed_ms),
                                    format_size(entry.size_bytes) if entry.size_bytes is not None else "—"])
            item.setForeground(1, QColor(theme.method_color(entry.method)))
            item.setForeground(3, QColor(theme.status_color(entry.status_code)))
            item.setForeground(0, QColor(theme.text_faint))
            item.setToolTip(2, f"{entry.request_name}\n{entry.url}" if entry.request_name else entry.url)
            item.setData(0, Qt.ItemDataRole.UserRole, entry.request_id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, f"{entry.method} {entry.url} {status} {entry.request_name}".lower())
            self.tree.addTopLevelItem(item)
        if not entries:
            placeholder = QTreeWidgetItem(["", "", tr("No requests sent yet"), "", "", ""])
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tree.addTopLevelItem(placeholder)

    def _apply_filter(self, text: str) -> None:
        terms = text.lower().split()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            haystack = item.data(0, Qt.ItemDataRole.UserRole + 1) or ""
            item.setHidden(not all(term in haystack for term in terms))

    def _on_double_click(self, item: QTreeWidgetItem) -> None:
        request_id = item.data(0, Qt.ItemDataRole.UserRole)
        if request_id:
            self.open_request.emit(request_id)
            self.accept()

    def _clear(self) -> None:
        if ConfirmDialog.ask(self, tr("Clear history?"), tr("All history entries of this project will be removed."),
                             tr("Clear")):
            self._on_clear()
            self._fill([])
