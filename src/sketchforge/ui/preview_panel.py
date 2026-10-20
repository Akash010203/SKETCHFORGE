"""Read-only views of what the design currently exports: HTML, CSS, Design IR JSON.

The panel contains four tabs:
  HTML        – the generated HTML source (plain text, monospace)
  CSS         – the generated CSS source
  Design IR   – the Design IR serialised as JSON
  Live Preview – the generated HTML rendered in an embedded QWebEngineView
                 (interactive, full browser engine).  Falls back gracefully if
                 QtWebEngineWidgets is not installed.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from sketchforge.application.app_controller import AppController
from sketchforge.design_ir.serialization import to_json

log = logging.getLogger(__name__)

# Try to import the WebEngine; it is an optional dependency.
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore[attr-defined]
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False
    log.info("QtWebEngineWidgets not available – live preview tab will show a notice.")


def _code_view() -> QPlainTextEdit:
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    view.setFont(font)
    return view


class _LivePreviewTab(QWidget):
    """Container for the embedded browser preview.

    Uses QWebEngineView when available; shows a helpful notice otherwise.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _HAS_WEBENGINE:
            self._view: QWebEngineView = QWebEngineView()
            # Disable external navigation so the view stays sandboxed.
            self._view.setUrl("about:blank")  # type: ignore[arg-type]
            layout.addWidget(self._view)
            self._available = True
        else:
            notice = QLabel(
                "<b>Live Preview is not available.</b><br>"
                "Install <code>PySide6-WebEngine</code> to enable the interactive preview:<br>"
                "<code>pip install PySide6-WebEngine</code>"
            )
            notice.setWordWrap(True)
            notice.setContentsMargins(16, 16, 16, 16)
            layout.addWidget(notice)
            self._available = False

    def load_html(self, html: str) -> None:
        """Render ``html`` in the embedded browser (no-op if unavailable)."""
        if self._available:
            # setHtml is limited to ~2 MB; for larger payloads use setContent.
            self._view.setHtml(html)

    def clear(self) -> None:
        if self._available:
            self._view.setHtml("<html><body></body></html>")


class PreviewPanel(QTabWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller

        self.html_view = _code_view()
        self.css_view = _code_view()
        self.json_view = _code_view()
        self._live = _LivePreviewTab()

        self.addTab(self.html_view, "HTML")
        self.addTab(self.css_view, "CSS")
        self.addTab(self.json_view, "Design IR")
        self.addTab(self._live, "Live Preview")

        # Only refresh the live tab when it is actually visible (avoid
        # unnecessary WebEngine reloads while the user is on another tab).
        self.currentChanged.connect(self._on_tab_changed)
        self._pending_html: str | None = None

    def refresh(self) -> None:
        if not self.controller.has_project:
            for v in (self.html_view, self.css_view, self.json_view):
                v.clear()
            self._live.clear()
            self._pending_html = None
            return

        rendered = self.controller.render()
        self.html_view.setPlainText(rendered.html)
        self.css_view.setPlainText(rendered.css)
        self.json_view.setPlainText(to_json(self.controller.document))

        # Update live view immediately if it is the current tab; otherwise
        # queue it so we don't pay the WebEngine cost unnecessarily.
        if self.currentWidget() is self._live:
            self._live.load_html(rendered.html)
            self._pending_html = None
        else:
            self._pending_html = rendered.html

    def _on_tab_changed(self, index: int) -> None:
        if self.widget(index) is self._live and self._pending_html is not None:
            self._live.load_html(self._pending_html)
            self._pending_html = None
