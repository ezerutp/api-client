from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.themes.manager import current_theme

ROLE_ENTRY = Qt.ItemDataRole.UserRole + 1


@dataclass
class PaletteEntry:
    title: str
    action: Callable[[], object]
    subtitle: str = ""
    shortcut: str = ""
    method: str | None = None

    @property
    def haystack(self) -> str:
        return f"{self.method or ''} {self.title} {self.subtitle}".lower()


class _Delegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 34)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        entry: PaletteEntry = index.data(ROLE_ENTRY)
        theme = current_theme()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 1, -2, -1)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.bg_selected))
            painter.drawRoundedRect(rect, 6, 6)
        x = rect.left() + 12
        font = QFont(option.font)
        if entry.method:
            badge_font = QFont(font)
            badge_font.setPixelSize(10)
            badge_font.setWeight(QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.setPen(QColor(theme.method_color(entry.method)))
            painter.drawText(QRect(x, rect.top(), 56, rect.height()), Qt.AlignmentFlag.AlignVCenter, entry.method)
            x += 60
        painter.setFont(font)
        painter.setPen(QColor(theme.text))
        title_width = painter.fontMetrics().horizontalAdvance(entry.title)
        painter.drawText(QRect(x, rect.top(), rect.width() - x, rect.height()), Qt.AlignmentFlag.AlignVCenter,
                         entry.title)
        right = rect.right() - 12
        small = QFont(font)
        small.setPixelSize(11)
        painter.setFont(small)
        if entry.shortcut:
            painter.setPen(QColor(theme.text_faint))
            painter.drawText(QRect(right - 140, rect.top(), 140, rect.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, entry.shortcut)
            right -= 150
        if entry.subtitle:
            painter.setPen(QColor(theme.text_faint))
            start = x + title_width + 14
            sub_rect = QRect(start, rect.top(), max(0, right - start), rect.height())
            text = painter.fontMetrics().elidedText(entry.subtitle, Qt.TextElideMode.ElideLeft, sub_rect.width())
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)
        painter.restore()


class CommandPalette(QDialog):
    def __init__(self, parent: QWidget, entries: list[PaletteEntry], placeholder: str | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._entries = entries
        self._chosen: PaletteEntry | None = None
        frame = QFrame()
        frame.setObjectName("CommandPalette")
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder or tr("Search requests and actions…"))
        self.search.textChanged.connect(self._filter)
        self.search.installEventFilter(self)
        self.list = QListWidget()
        self.list.setItemDelegate(_Delegate(self.list))
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.itemActivated.connect(self._choose)
        self.list.itemClicked.connect(self._choose)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        inner.addWidget(self.search)
        inner.addWidget(self.list)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        width = min(640, parent.width() - 80)
        self.resize(width, 400)
        top_left = parent.mapToGlobal(parent.rect().topLeft())
        self.move(top_left.x() + (parent.width() - width) // 2, top_left.y() + 70)
        self._filter("")
        self.search.setFocus()

    def _filter(self, text: str) -> None:
        terms = text.lower().split()
        self.list.clear()
        for entry in self._entries:
            if all(term in entry.haystack for term in terms):
                item = QListWidgetItem(entry.title)
                item.setData(ROLE_ENTRY, entry)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.search and isinstance(event, QKeyEvent) and event.type() == QKeyEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                count = self.list.count()
                if count:
                    self.list.setCurrentRow((self.list.currentRow() + step) % count)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.list.currentItem()
                if item is not None:
                    self._choose(item)
                return True
        return super().eventFilter(watched, event)

    def _choose(self, item: QListWidgetItem) -> None:
        self._chosen = item.data(ROLE_ENTRY)
        self.accept()

    @staticmethod
    def run(parent: QWidget, entries: list[PaletteEntry], placeholder: str | None = None) -> None:
        palette = CommandPalette(parent, entries, placeholder)
        if palette.exec() == QDialog.DialogCode.Accepted and palette._chosen is not None:
            palette._chosen.action()
