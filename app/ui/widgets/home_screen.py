from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from app import APP_NAME, APP_VERSION
from app.i18n import tr
from app.repositories.recent_projects_repository import RecentProject
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import apply_icon, button, hbox, icon_button, label, vbox
from app.ui.widgets.top_bar import LogoBadge
from app.utils.formatting import format_relative_time


class _RecentCard(QFrame):
    clicked = Signal(str)
    remove_clicked = Signal(str)

    def __init__(self, project: RecentProject) -> None:
        super().__init__()
        self.setObjectName("RecentCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._path = project.path
        exists = Path(project.path).exists()
        self._icon = QLabel()
        name = label(project.name, "RecentName")
        path = label(project.path if exists else tr("{path}  (missing)", path=project.path), "RecentPath")
        path.setToolTip(project.path)
        when = label(format_relative_time(project.last_opened), "RecentTime")
        self._remove = icon_button("close", tr("Remove from recent projects"), size=14,
                                   on_click=lambda: self.remove_clicked.emit(self._path))
        self._remove.setVisible(False)
        self.setLayout(hbox(self._icon, 4, vbox(name, path, spacing=1), None, when, self._remove,
                            spacing=10, margins=(12, 9, 10, 9)))
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self._icon.setPixmap(icons.pixmap("folder", current_theme().text_muted, 18))
        apply_icon(self._remove)

    def enterEvent(self, event) -> None:
        self._remove.setVisible(True)

    def leaveEvent(self, event) -> None:
        self._remove.setVisible(False)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self._path)


class HomeScreen(QWidget):
    open_project = Signal()
    create_project = Signal()
    open_recent = Signal(str)
    remove_recent = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HomeScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cards: list[_RecentCard] = []
        self.logo = LogoBadge(52, 30)
        title = label(APP_NAME, "HomeTitle")
        subtitle = label(tr("Test your APIs without the clutter."), "HomeSubtitle")
        self._open = button(tr("Open Project"), "primary", icon_name="folder-open", on_click=self.open_project.emit)
        self._create = button(tr("Create Project"), icon_name="plus", on_click=self.create_project.emit)
        for b in (self._open, self._create):
            b.setMinimumHeight(38)
            b.setMinimumWidth(170)

        self._recent_list = QVBoxLayout()
        self._recent_list.setSpacing(2)
        self._recent_empty = label(tr("No recent projects yet. Open a backend folder to get started."), "Faint")

        column = QWidget()
        column.setMaximumWidth(600)
        column.setMinimumWidth(420)
        column_layout = vbox(
            self.logo, 14, title, subtitle, 26, hbox(None, self._open, self._create, None, spacing=10), 40,
            label(tr("RECENT PROJECTS"), "SectionLabel"), 4, self._recent_list, self._recent_empty, 28,
            label(tr("Ctrl+O  open project   ·   Ctrl+Shift+O  create project   ·   v{version}", version=APP_VERSION),
                  "Hint"),
            spacing=4,
        )
        for widget in (self.logo, title, subtitle):
            column_layout.setAlignment(widget, Qt.AlignmentFlag.AlignHCenter)
        column.setLayout(column_layout)
        hint = column_layout.itemAt(column_layout.count() - 1).widget()
        column_layout.setAlignment(hint, Qt.AlignmentFlag.AlignHCenter)

        content = QWidget()
        content.setLayout(vbox(None, hbox(None, column, None), None, margins=(24, 24, 24, 24)))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def set_recent(self, projects: list[RecentProject]) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        for project in projects:
            card = _RecentCard(project)
            card.clicked.connect(self.open_recent)
            card.remove_clicked.connect(self.remove_recent)
            self._recent_list.addWidget(card)
            self._cards.append(card)
        self._recent_empty.setVisible(not projects)

    def refresh_theme(self) -> None:
        theme = current_theme()
        self.logo.refresh_theme()
        self._open.setIcon(icons.icon("folder-open", theme.accent_text))
        self._create.setIcon(icons.icon("plus", theme.text_muted))
        for card in self._cards:
            card.refresh_theme()


