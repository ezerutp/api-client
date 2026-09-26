"""A compact code editor: line numbers, auto-indent, error line marker."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QTextCursor, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from app.themes.manager import current_theme
from app.ui.helpers import monospace_font, set_prop

INDENT = "  "
_PAIRS = {"{": "}", "[": "]"}


def is_send_shortcut(event: QKeyEvent) -> bool:
    return event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and bool(
        event.modifiers() & Qt.KeyboardModifier.ControlModifier
    )


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    font_size_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None, *, read_only: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("CodeEditor")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setReadOnly(read_only)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
            if read_only else Qt.TextInteractionFlag.TextEditorInteraction
        )
        self.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self._error_line: int | None = None
        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margins)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._refresh_selections)
        self.set_font_size(13)

    # -- appearance -----------------------------------------------------------------

    def set_font_size(self, size: int) -> None:
        font = monospace_font(size)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * len(INDENT))
        self._update_margins()

    def set_wrap(self, wrap: bool) -> None:
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrap else QPlainTextEdit.LineWrapMode.NoWrap)

    def set_error_line(self, line: int | None) -> None:
        self._error_line = line
        set_prop(self, "error", line is not None)
        self._refresh_selections()

    def line_number_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 20 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margins(self) -> None:
        self.setViewportMargins(self.line_number_width(), 4, 4, 4)

    def _update_line_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents = self.contentsRect()
        self._line_area.setGeometry(QRect(contents.left(), contents.top(), self.line_number_width(), contents.height()))

    def paint_line_numbers(self, event) -> None:
        theme = current_theme()
        painter = QPainter(self._line_area)
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        offset = self.contentOffset()
        top = round(self.blockBoundingGeometry(block).translated(offset).top()) + 4
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        width = self._line_area.width() - 10
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if self._error_line is not None and number + 1 == self._error_line:
                    color = theme.danger
                elif number == current and not self.isReadOnly():
                    color = theme.text_muted
                else:
                    color = theme.text_faint
                painter.setPen(QColor(color))
                painter.drawText(0, top, width, height, Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1
        painter.setPen(QColor(theme.border))
        x = self._line_area.width() - 1
        painter.drawLine(x, 0, x, self._line_area.height())

    def _refresh_selections(self) -> None:
        theme = current_theme()
        selections: list[QTextEdit.ExtraSelection] = []
        if self._error_line is not None:
            block = self.document().findBlockByNumber(self._error_line - 1)
            if block.isValid():
                selection = QTextEdit.ExtraSelection()
                color = QColor(theme.danger)
                color.setAlpha(40)
                selection.format.setBackground(color)
                selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
                selection.cursor = QTextCursor(block)
                selections.append(selection)
        self.setExtraSelections(selections)
        self._line_area.update()

    # -- editing behaviour ----------------------------------------------------------

    def event(self, event: QEvent) -> bool:
        # Let window shortcuts (Ctrl+Enter = send) win over the text editor.
        if event.type() == QEvent.Type.ShortcutOverride and isinstance(event, QKeyEvent) and is_send_shortcut(event):
            event.ignore()
            return False
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if is_send_shortcut(event):
            event.ignore()
            return
        if self.isReadOnly():
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key.Key_Tab and not event.modifiers():
            self._indent_selection() if self.textCursor().hasSelection() else self.insertPlainText(INDENT)
            return
        if key == Qt.Key.Key_Backtab:
            self._dedent_selection()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._newline_with_indent()
            return
        if event.text() in ("}", "]"):
            self._dedent_closing_bracket(event.text())
            return
        super().keyPressEvent(event)

    def _current_indent(self) -> str:
        text = self.textCursor().block().text()
        return text[: len(text) - len(text.lstrip(" "))]

    def _newline_with_indent(self) -> None:
        cursor = self.textCursor()
        block_text = cursor.block().text()
        before = block_text[: cursor.positionInBlock()].rstrip()
        after = block_text[cursor.positionInBlock():].lstrip()
        indent = self._current_indent()
        cursor.beginEditBlock()
        if before and before[-1] in _PAIRS:
            if after and after[0] == _PAIRS[before[-1]]:
                cursor.insertText("\n" + indent + INDENT)
                position = cursor.position()
                cursor.insertText("\n" + indent)
                cursor.setPosition(position)
            else:
                cursor.insertText("\n" + indent + INDENT)
        else:
            cursor.insertText("\n" + indent)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _dedent_closing_bracket(self, char: str) -> None:
        cursor = self.textCursor()
        before = cursor.block().text()[: cursor.positionInBlock()]
        cursor.beginEditBlock()
        if before and not before.strip() and before.endswith(INDENT):
            for _ in INDENT:
                cursor.deletePreviousChar()
        cursor.insertText(char)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _selected_blocks(self) -> tuple[QTextCursor, int, int]:
        cursor = self.textCursor()
        doc = self.document()
        start = doc.findBlock(cursor.selectionStart()).blockNumber()
        end_block = doc.findBlock(cursor.selectionEnd())
        end = end_block.blockNumber()
        if cursor.selectionEnd() == end_block.position() and end > start:
            end -= 1
        return cursor, start, end

    def _indent_selection(self) -> None:
        cursor, start, end = self._selected_blocks()
        cursor.beginEditBlock()
        for number in range(start, end + 1):
            line = QTextCursor(self.document().findBlockByNumber(number))
            line.insertText(INDENT)
        cursor.endEditBlock()

    def _dedent_selection(self) -> None:
        cursor, start, end = self._selected_blocks()
        cursor.beginEditBlock()
        for number in range(start, end + 1):
            block = self.document().findBlockByNumber(number)
            spaces = len(block.text()) - len(block.text().lstrip(" "))
            remove = min(spaces, len(INDENT))
            if remove:
                line = QTextCursor(block)
                line.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, remove)
                line.removeSelectedText()
        cursor.endEditBlock()

    def set_text_preserving_undo(self, text: str) -> None:
        """Replace everything as one undoable step (used by Format)."""
        cursor = self.textCursor()
        position = cursor.position()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        cursor.setPosition(min(position, len(text)))
        self.setTextCursor(cursor)
