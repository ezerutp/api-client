from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import button, hbox, label, vbox

_SHORTCUTS = [
    ("Ctrl + N", "New request"),
    ("Ctrl + K", "Command palette"),
    ("Ctrl + Enter", "Send request"),
    ("Ctrl + L", "Focus URL"),
]


class EditorEmptyState(QWidget):
    """Shown in the editor area when no request tab is open."""

    new_request = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ContentArea")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._no_requests_icon = QLabel()
        self._select_icon = QLabel()

        no_requests = self._page(
            self._no_requests_icon, 8, label("No requests yet", "EmptyTitle"),
            label("Create your first request to start testing your API.", "EmptyText"), 12,
            button("New Request", "primary", icon_name="plus", on_click=self.new_request.emit),
        )
        shortcuts = QWidget()
        rows = vbox(spacing=8)
        for keys, text in _SHORTCUTS:
            key = label(keys, "ShortcutKey")
            key.setFixedWidth(96)
            key.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rows.addLayout(hbox(label(text, "Muted"), None, key, spacing=24))
        shortcuts.setLayout(rows)
        shortcuts.setFixedWidth(300)
        select = self._page(
            self._select_icon, 8, label("Select a request", "EmptyTitle"),
            label("Pick an endpoint from the sidebar or press Ctrl + K to search.", "EmptyText"), 18, shortcuts,
        )
        self.pages = QStackedWidget()
        self.pages.addWidget(no_requests)
        self.pages.addWidget(select)
        self.setLayout(vbox(self.pages))
        self.refresh_theme()

    @staticmethod
    def _page(*widgets) -> QWidget:
        page = QWidget()
        column = vbox(None, *widgets, None, spacing=6)
        for i in range(column.count()):
            widget = column.itemAt(i).widget()
            if widget is not None:
                column.setAlignment(widget, Qt.AlignmentFlag.AlignHCenter)
        page.setLayout(column)
        return page

    def set_has_requests(self, has_requests: bool) -> None:
        self.pages.setCurrentIndex(1 if has_requests else 0)

    def refresh_theme(self) -> None:
        theme = current_theme()
        self._no_requests_icon.setPixmap(icons.pixmap("inbox", theme.text_faint, 36, 1.5))
        self._select_icon.setPixmap(icons.pixmap("zap", theme.text_faint, 36, 1.5))
