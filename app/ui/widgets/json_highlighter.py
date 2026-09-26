from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument

from app.themes.manager import current_theme

_TOKEN = re.compile(
    r'(?P<string>"(?:[^"\\]|\\.)*")(?P<colon>\s*:)?'
    r"|(?P<variable>\{\{[^{}]*\}\})"
    r"|(?P<number>-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)"
    r"|(?P<keyword>\b(?:true|false|null)\b)"
    r"|(?P<punct>[{}\[\],:])"
)
_VARIABLE_IN_STRING = re.compile(r"\{\{[^{}]*\}\}")


class JsonHighlighter(QSyntaxHighlighter):
    """Line based JSON highlighting; also marks ``{{variables}}``."""

    def __init__(self, document: QTextDocument | None = None) -> None:
        super().__init__(document)
        self._formats: dict[str, QTextCharFormat] = {}
        self.refresh_theme()

    def refresh_theme(self) -> None:
        theme = current_theme()

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            return f

        self._formats = {
            "key": fmt(theme.syntax_key),
            "string": fmt(theme.syntax_string),
            "number": fmt(theme.syntax_number),
            "keyword": fmt(theme.syntax_keyword),
            "punct": fmt(theme.syntax_punct),
            "variable": fmt(theme.syntax_variable, bold=True),
        }
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        if len(text) > 20_000:
            return
        for match in _TOKEN.finditer(text):
            kind = match.lastgroup
            if match.group("string") is not None:
                start, end = match.span("string")
                is_key = match.group("colon") is not None
                self.setFormat(start, end - start, self._formats["key" if is_key else "string"])
                for var in _VARIABLE_IN_STRING.finditer(match.group("string")):
                    self.setFormat(start + var.start(), var.end() - var.start(), self._formats["variable"])
                if is_key:
                    colon_start, colon_end = match.span("colon")
                    self.setFormat(colon_start, colon_end - colon_start, self._formats["punct"])
            elif kind:
                self.setFormat(match.start(), match.end() - match.start(), self._formats[kind])
