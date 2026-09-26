from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QToolButton, QWidget

from app import APP_NAME
from app.models.environment import Environment
from app.repositories.recent_projects_repository import RecentProject
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import apply_icon, hbox, icon_button, label


def environment_color(name: str) -> str:
    """Production-looking environments are red so nobody sends a DELETE there by accident."""
    theme = current_theme()
    lower = name.lower()
    if "prod" in lower or lower in ("live", "prd"):
        return theme.danger
    if any(tag in lower for tag in ("dev", "stag", "qa", "test", "uat", "pre")):
        return theme.warning
    return theme.success


def dot_icon(color: str, size: int = 8) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size * 2, size * 2)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class LogoBadge(QLabel):
    def __init__(self, size: int = 26, icon_size: int = 16) -> None:
        super().__init__()
        self.setObjectName("LogoBadge")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_size = icon_size
        self.setStyleSheet(f"border-radius: {max(6, size // 4)}px;")
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.setPixmap(icons.pixmap("box", current_theme().accent_text, self._icon_size, 2.0))


class TopBar(QWidget):
    environment_selected = Signal(str)
    manage_environments = Signal()
    open_history = Signal()
    open_settings = Signal()
    open_palette = Signal()
    open_project = Signal()
    create_project = Signal()
    open_recent = Signal(str)
    edit_project = Signal()
    reveal_folder = Signal()
    reload_project = Signal()
    close_project = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(50)
        self._recent: list[RecentProject] = []
        self._current_env: str | None = None

        self.logo = LogoBadge()
        title = label(APP_NAME, "AppTitle")
        self._separator = QFrame()
        self._separator.setObjectName("TopBarSeparator")
        self._separator.setFixedSize(1, 20)

        self.project_button = QToolButton()
        self.project_button.setObjectName("ProjectButton")
        self.project_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.project_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.project_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._project_menu = QMenu(self.project_button)
        self._project_menu.aboutToShow.connect(self._build_project_menu)
        self.project_button.setMenu(self._project_menu)

        self.env_button = QToolButton()
        self.env_button.setObjectName("EnvButton")
        self.env_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.env_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.env_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.env_button.setToolTip("Active environment")
        self.env_button.setMinimumWidth(120)
        self._env_menu = QMenu(self.env_button)
        self.env_button.setMenu(self._env_menu)

        self._env_separator = QFrame()
        self._env_separator.setObjectName("TopBarSeparator")
        self._env_separator.setFixedSize(1, 20)
        self.palette_button = icon_button("command", "Command palette (Ctrl+K)", on_click=self.open_palette.emit)
        self.history_button = icon_button("history", "History (Ctrl+H)", on_click=self.open_history.emit)
        self.settings_button = QToolButton()
        self.settings_button.setText("Settings")
        self.settings_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("Settings (Ctrl+,)")
        self.settings_button.setProperty("icon_name", "settings")
        self.settings_button.clicked.connect(self.open_settings.emit)

        self.setLayout(hbox(
            self.logo, 2, title, 8, self._separator, 4, self.project_button, None,
            self.env_button, 6, self._env_separator, 6, self.palette_button, self.history_button,
            self.settings_button, spacing=6, margins=(14, 0, 12, 0),
        ))
        self.set_project(None)

    # -- API ------------------------------------------------------------------------

    def set_project(self, name: str | None) -> None:
        has_project = name is not None
        for widget in (self._separator, self.project_button, self.env_button, self._env_separator,
                       self.history_button, self.palette_button):
            widget.setVisible(has_project)
        self.project_button.setText(name or "")

    def set_recent(self, recent: list[RecentProject]) -> None:
        self._recent = recent

    def set_environments(self, environments: list[Environment], current: str | None) -> None:
        self._current_env = current
        self._env_menu.clear()
        group = QActionGroup(self._env_menu)
        for env in environments:
            action = QAction(dot_icon(environment_color(env.name)), env.display_name, self._env_menu)
            action.setCheckable(True)
            action.setChecked(env.name == current)
            action.triggered.connect(lambda _=False, n=env.name: self.environment_selected.emit(n))
            group.addAction(action)
            self._env_menu.addAction(action)
        if not environments:
            placeholder = self._env_menu.addAction("No environments")
            placeholder.setEnabled(False)
        self._env_menu.addSeparator()
        self._env_menu.addAction("Manage environments…", self.manage_environments.emit)
        display = next((e.display_name for e in environments if e.name == current), "No environment")
        self.env_button.setText(f" {display}")
        self.env_button.setIcon(dot_icon(environment_color(current) if current else current_theme().text_faint))

    def refresh_theme(self) -> None:
        theme = current_theme()
        self.logo.refresh_theme()
        self.project_button.setIcon(icons.icon("chevron-down", theme.text_muted, 14))
        for widget in (self.history_button, self.palette_button, self.settings_button):
            apply_icon(widget)
        if self._current_env:
            self.env_button.setIcon(dot_icon(environment_color(self._current_env)))

    def _build_project_menu(self) -> None:
        menu = self._project_menu
        menu.clear()
        menu.addAction("Project settings…", self.edit_project.emit)
        menu.addAction("Reveal api-client folder", self.reveal_folder.emit)
        menu.addAction("Reload from disk", self.reload_project.emit)
        menu.addSeparator()
        menu.addAction("Open project…", self.open_project.emit)
        menu.addAction("Create project…", self.create_project.emit)
        others = self._recent[:8]
        if others:
            recent_menu = menu.addMenu("Open recent")
            for project in others:
                action = recent_menu.addAction(f"{project.name}    {project.path}")
                action.triggered.connect(lambda _=False, p=project.path: self.open_recent.emit(p))
        menu.addSeparator()
        menu.addAction("Close project", self.close_project.emit)
