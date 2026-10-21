"""Live HTML preview and source views for generated HTML, CSS and Design IR."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # WebEngine is supplied by the optional PySide6 Addons package.
    QUrl = None
    QWebEngineView = None

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
        self.web_view = QWebEngineView() if QWebEngineView is not None else QWidget()
        if QWebEngineView is None:
            fallback = QVBoxLayout(self.web_view)
            fallback.addWidget(QLabel(
                "Live preview requires the optional PySide6 WebEngine component. "
                "Install SketchForge with the 'ui' extra to enable it."
            ))

        self.addTab(self.html_view, "HTML")
        self.addTab(self.web_view, "Web")
        self.addTab(self.css_view, "CSS")
        self.addTab(self.json_view, "Design IR")

    def refresh(self) -> None:
        if not self.controller.has_project:
            for v in (self.html_view, self.css_view, self.json_view):
                v.clear()
            if QWebEngineView is not None:
                self.web_view.setHtml("")
            return

        rendered = self.controller.render()
        self.html_view.setPlainText(rendered.html)
        self.css_view.setPlainText(rendered.css)
        self.json_view.setPlainText(to_json(self.controller.document))
        if QWebEngineView is not None:
            self.web_view.setHtml(rendered.html, QUrl("about:blank"))

