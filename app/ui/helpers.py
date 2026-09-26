"""Small factories so widgets share the same look without repeating setup code."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QPushButton, QToolButton, QVBoxLayout, QWidget

from app.themes.manager import current_theme
from app.ui import icons

_MONO_CANDIDATES = ["JetBrains Mono", "Cascadia Code", "Cascadia Mono", "Fira Code", "Source Code Pro",
                    "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"]
_mono_family: str | None = None


def monospace_font(size: int = 13) -> QFont:
    global _mono_family
    if _mono_family is None:
        available = set(QFontDatabase.families())
        _mono_family = next((f for f in _MONO_CANDIDATES if f in available), "")
    font = QFont(_mono_family) if _mono_family else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPixelSize(size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_prop(widget: QWidget, name: str, value: object) -> None:
    if widget.property(name) != value:
        widget.setProperty(name, value)
        repolish(widget)


def label(text: str = "", object_name: str | None = None, *, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, variant: str | None = None, *, icon_name: str | None = None,
           on_click: Callable[[], object] | None = None) -> QPushButton:
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        widget.setProperty("variant", variant)
    if icon_name:
        theme = current_theme()
        color = theme.accent_text if variant in ("primary", "danger") else theme.text_muted
        widget.setIcon(icons.icon(icon_name, color))
    if on_click is not None:
        widget.clicked.connect(lambda: on_click())
    return widget


def icon_button(icon_name: str, tooltip: str, *, on_click: Callable[[], object] | None = None,
                size: int = 16, object_name: str | None = None) -> QToolButton:
    widget = QToolButton()
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setToolTip(tooltip)
    widget.setAutoRaise(True)
    if object_name:
        widget.setObjectName(object_name)
    widget.setProperty("icon_name", icon_name)
    widget.setProperty("icon_size", size)
    apply_icon(widget)
    if on_click is not None:
        widget.clicked.connect(lambda: on_click())
    return widget


def apply_icon(widget: QToolButton, color: str | None = None) -> None:
    theme = current_theme()
    name = widget.property("icon_name")
    size = widget.property("icon_size") or 16
    if name:
        widget.setIcon(icons.icon(name, color or theme.text_muted, size, active_color=theme.text))
        widget.setIconSize(icons.icon_size(size))


def hbox(*items: QWidget | QLayout | int | None, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QHBoxLayout:
    layout = QHBoxLayout()
    _fill(layout, items, spacing, margins)
    return layout


def vbox(*items: QWidget | QLayout | int | None, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QVBoxLayout:
    layout = QVBoxLayout()
    _fill(layout, items, spacing, margins)
    return layout


def _fill(layout: QHBoxLayout | QVBoxLayout, items, spacing: int, margins: tuple[int, int, int, int]) -> None:
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    for item in items:
        if item is None:
            layout.addStretch(1)
        elif isinstance(item, int):
            layout.addSpacing(item)
        elif isinstance(item, QLayout):
            layout.addLayout(item)
        else:
            layout.addWidget(item)


class Debouncer(QObject):
    """Calls ``callback`` once, ``delay_ms`` after the last ``trigger()``."""

    def __init__(self, delay_ms: int, callback: Callable[[], object], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(callback)

    def trigger(self) -> None:
        self._timer.start()

    def cancel(self) -> None:
        self._timer.stop()

    def set_delay(self, delay_ms: int) -> None:
        self._timer.setInterval(delay_ms)

    def flush(self) -> bool:
        if self._timer.isActive():
            self._timer.stop()
            self._timer.timeout.emit()
            return True
        return False

    @property
    def pending(self) -> bool:
        return self._timer.isActive()
