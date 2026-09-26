from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget


class Toast(QLabel):
    """Small non-blocking notification at the bottom center of its parent."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, duration_ms: int = 2200) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.raise_()
        self.show()
        self._animation.stop()
        self._animation.setDuration(150)
        self._animation.setStartValue(self._effect.opacity() if self.isVisible() else 0.0)
        self._animation.setEndValue(1.0)
        self._animation.start()
        self._hide_timer.start(duration_ms)

    def _fade_out(self) -> None:
        self._animation.stop()
        self._animation.setDuration(300)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.finished.connect(self._after_fade)
        self._animation.start()

    def _after_fade(self) -> None:
        self._animation.finished.disconnect(self._after_fade)
        if self._effect.opacity() < 0.05:
            self.hide()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 36)
