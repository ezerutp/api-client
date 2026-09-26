"""Pill-shaped on/off switch with its label, painted from the active theme."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QWidget

from app.themes.manager import current_theme

_TRACK_W, _TRACK_H, _GAP = 30, 16, 8


class ToggleSwitch(QAbstractButton):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 0.0  # knob position: 0 = off, 1 = on
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(120)
        self._animation.valueChanged.connect(self._on_animation_step)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(_TRACK_W + (_GAP + text_width if self.text() else 0) + 2, max(_TRACK_H, self.fontMetrics().height()) + 4)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API
        super().setChecked(checked)
        self._animation.stop()
        self._offset = 1.0 if checked else 0.0
        self.update()

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def _on_animation_step(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        theme = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(1, (self.height() - _TRACK_H) / 2, _TRACK_W, _TRACK_H)
        off, on = QColor(theme.border_strong), QColor(theme.accent)
        t = self._offset
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(int(off.red() + (on.red() - off.red()) * t),
                                int(off.green() + (on.green() - off.green()) * t),
                                int(off.blue() + (on.blue() - off.blue()) * t)))
        painter.drawRoundedRect(track, _TRACK_H / 2, _TRACK_H / 2)
        knob = _TRACK_H - 4
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(track.left() + 2 + (_TRACK_W - knob - 4) * t, track.top() + 2, knob, knob))
        if self.text():
            painter.setPen(QColor(theme.text if self.underMouse() or self.isChecked() else theme.text_muted))
            text_rect = self.rect().adjusted(_TRACK_W + _GAP + 1, 0, 0, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        painter.end()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().leaveEvent(event)
        self.update()
