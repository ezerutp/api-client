"""Single line URL field that highlights ``{{variables}}`` (defined vs. missing)."""

from __future__ import annotations

import re
from html import escape

from PySide6.QtCore import QEvent, QMimeData, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import QFrame, QPlainTextEdit, QToolTip, QWidget

from app.i18n import tr
from app.services.variable_service import VARIABLE_PATTERN, VariableContext, VariableResolver
from app.themes.manager import current_theme
from app.ui.widgets.code_editor import is_send_shortcut

_PATH_PARAM = re.compile(r"(?<!\{)\{[A-Za-z_][A-Za-z0-9_\-]*\}(?!\})")


class _UrlHighlighter(QSyntaxHighlighter):
    def __init__(self, editor: UrlEdit) -> None:
        super().__init__(editor.document())
        self._editor = editor

    def highlightBlock(self, text: str) -> None:
        theme = current_theme()
        context = self._editor.variable_context
        for match in VARIABLE_PATTERN.finditer(text):
            fmt = QTextCharFormat()
            if context.is_defined(match.group(1)):
                fmt.setForeground(QColor(theme.syntax_variable))
            else:
                fmt.setForeground(QColor(theme.danger))
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                fmt.setUnderlineColor(QColor(theme.danger))
            self.setFormat(match.start(), match.end() - match.start(), fmt)
        path_end = text.find("?")
        path = text if path_end < 0 else text[:path_end]
        for match in _PATH_PARAM.finditer(path):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(theme.syntax_keyword))
            self.setFormat(match.start(), match.end() - match.start(), fmt)
        if path_end >= 0:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(theme.text_muted))
            self.setFormat(path_end, 1, fmt)


class UrlEdit(QPlainTextEdit):
    text_changed = Signal(str)
    submitted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("UrlEdit")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.setFixedHeight(38)
        self.setMouseTracking(True)
        self.setPlaceholderText(tr("Enter URL, e.g. {{base_url}}/api/productos"))
        self.document().setDocumentMargin(0)
        self.variable_context = VariableContext()
        self._highlighter = _UrlHighlighter(self)
        self.textChanged.connect(lambda: self.text_changed.emit(self.text()))

    def text(self) -> str:
        return self.toPlainText()

    def set_text(self, text: str) -> None:
        self.blockSignals(True)
        self.setPlainText(text)
        self.blockSignals(False)
        self._highlighter.rehighlight()

    def set_variable_context(self, context: VariableContext) -> None:
        self.variable_context = context
        self._highlighter.rehighlight()

    def refresh_theme(self) -> None:
        self._highlighter.rehighlight()

    def select_all_and_focus(self) -> None:
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.selectAll()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        line_height = self.fontMetrics().height()
        top = max(0, (self.viewport().height() + self.viewportMargins().top() - line_height) // 2)
        self.setViewportMargins(6, top, 6, 0)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and isinstance(event, QKeyEvent) and is_send_shortcut(event):
            event.ignore()
            return False
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if is_send_shortcut(event):
            event.ignore()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source: QMimeData) -> None:
        text = " ".join(source.text().split()) if source.hasText() else ""
        self.textCursor().insertText(text.strip())

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        cursor = self.cursorForPosition(event.position().toPoint())
        position = cursor.position()
        for match in VARIABLE_PATTERN.finditer(self.text()):
            if match.start() <= position <= match.end():
                QToolTip.showText(event.globalPosition().toPoint(), self._describe(match.group(1)), self)
                return
        QToolTip.hideText()

    def _describe(self, name: str) -> str:
        context = self.variable_context
        env = escape(context.environment or tr("no environment"))
        if not context.is_defined(name):
            return tr("<b>{name}</b> is not defined in <i>{env}</i>", name="{{" + name + "}}", env=env)
        if context.is_secret(name):
            return f"<b>{name}</b> = •••••• <span style='opacity:.7'>({tr('secret')} · {env})</span>"
        try:
            value = VariableResolver(context).resolve_variable(name)
        except Exception as exc:
            value = str(exc)
        return f"<b>{name}</b> = {escape(value)} <span style='opacity:.7'>({env})</span>"

    def move_cursor_to_end(self) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
