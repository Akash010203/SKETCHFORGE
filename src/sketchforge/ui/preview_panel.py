"""Static source views for the design's HTML, CSS and Design IR exports.

The central SVG canvas is the live interactive preview and editing surface. Keeping generated
source in plain-text views avoids embedding a second browser engine in the desktop application.
"""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QPlainTextEdit, QTabWidget

from sketchforge.application.app_controller import AppController
from sketchforge.design_ir.serialization import to_json

def _code_view() -> QPlainTextEdit:
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    view.setFont(font)
    return view


class PreviewPanel(QTabWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller

        self.html_view = _code_view()
        self.css_view = _code_view()
        self.json_view = _code_view()

        self.addTab(self.html_view, "HTML")
        self.addTab(self.css_view, "CSS")
        self.addTab(self.json_view, "Design IR")

    def refresh(self) -> None:
        if not self.controller.has_project:
            for v in (self.html_view, self.css_view, self.json_view):
                v.clear()
            return

        rendered = self.controller.render()
        self.html_view.setPlainText(rendered.html)
        self.css_view.setPlainText(rendered.css)
        self.json_view.setPlainText(to_json(self.controller.document))

