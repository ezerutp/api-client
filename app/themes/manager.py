from __future__ import annotations

from string import Template

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from app.themes.theme import DARK, LIGHT, THEMES, Theme
from app.utils.resources import resource_path


class ThemeManager(QObject):
    """Owns the active theme and re-styles the application when it changes."""

    theme_changed = Signal(object)

    _instance: ThemeManager | None = None

    def __init__(self) -> None:
        super().__init__()
        self._theme: Theme = DARK
        self._preference = "dark"
        self._template = Template(resource_path("themes", "style.qss").read_text(encoding="utf-8"))
        ThemeManager._instance = self

    @classmethod
    def instance(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def preference(self) -> str:
        return self._preference

    @property
    def theme(self) -> Theme:
        return self._theme

    def apply(self, preference: str, ui_font_size: int = 13, editor_font_size: int = 13) -> None:
        self._preference = preference
        self._theme = self._resolve(preference)
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        app.setPalette(self._palette(self._theme))
        tokens = self._theme.tokens() | {"font_size": f"{ui_font_size}px", "editor_font_size": f"{editor_font_size}px"}
        tokens |= self._write_qss_icons(self._theme)
        app.setStyleSheet(self._template.substitute(tokens))
        self.theme_changed.emit(self._theme)

    @staticmethod
    def _write_qss_icons(theme: Theme) -> dict[str, str]:
        """QSS can only reference image files, so tinted SVGs are written to a cache folder."""
        from app.storage.paths import user_data_dir
        from app.ui.icons import svg_markup

        folder = user_data_dir() / "cache" / "icons" / theme.name
        folder.mkdir(parents=True, exist_ok=True)
        specs = {
            "icon_chevron": ("chevron-down", theme.text_muted, 2.0),
            "icon_chevron_right": ("chevron-right", theme.text_muted, 2.0),
            "icon_check": ("check", theme.accent_text, 3.0),
            "icon_minus": ("minus", theme.accent_text, 3.0),
            "icon_close": ("close", theme.text_faint, 2.0),
            "icon_close_hover": ("close", theme.text, 2.0),
        }
        tokens = {}
        for token, (name, color, stroke) in specs.items():
            path = folder / f"{token}.svg"
            markup = svg_markup(name, color, stroke)
            if not path.exists() or path.read_text(encoding="utf-8") != markup:
                path.write_text(markup, encoding="utf-8")
            tokens[token] = path.as_posix()
        return tokens

    @staticmethod
    def _resolve(preference: str) -> Theme:
        if preference == "system":
            hints = QGuiApplication.styleHints()
            return LIGHT if hints.colorScheme() == Qt.ColorScheme.Light else DARK
        return THEMES.get(preference, DARK)

    @staticmethod
    def _palette(theme: Theme) -> QPalette:
        palette = QPalette()
        roles = {
            QPalette.ColorRole.Window: theme.bg,
            QPalette.ColorRole.WindowText: theme.text,
            QPalette.ColorRole.Base: theme.bg_input,
            QPalette.ColorRole.AlternateBase: theme.bg_panel,
            QPalette.ColorRole.Text: theme.text,
            QPalette.ColorRole.Button: theme.bg_input,
            QPalette.ColorRole.ButtonText: theme.text,
            QPalette.ColorRole.Highlight: theme.accent_soft,
            QPalette.ColorRole.HighlightedText: theme.text,
            QPalette.ColorRole.ToolTipBase: theme.bg_elevated,
            QPalette.ColorRole.ToolTipText: theme.text,
            QPalette.ColorRole.PlaceholderText: theme.text_faint,
            QPalette.ColorRole.Link: theme.accent,
        }
        for role, color in roles.items():
            palette.setColor(role, QColor(color))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.text_faint))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.text_faint))
        return palette


def current_theme() -> Theme:
    return ThemeManager.instance().theme
