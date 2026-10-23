"""Source, design, and isolated live preview for generated project files."""

from __future__ import annotations

import html
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # Optional desktop component.
    QWebEngineSettings = None
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


class _PreviewView(QWebEngineView or QWidget):
    def __init__(self, owner: "PreviewPanel") -> None:
        super().__init__()
        self.owner = owner
        self.loadStarted.connect(lambda: owner._show_state("starting"))
        self.loadFinished.connect(owner._load_finished)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):  # noqa: N802
        if self.owner.project_root and ("error" in str(level).lower() or "uncaught" in message.lower()):
            self.owner.error_label.setText(f"Runtime error · {message} (line {line_number})")
            self.owner.runtime_bar.setVisible(True)


class PreviewPanel(QTabWidget):
    """Run the generated project's real files inside a sandboxed iframe."""

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.project_root: Path | None = None
        self._server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._project_url = ""

        self.html_view = _code_view()
        self.css_view = _code_view()
        self.json_view = _code_view()
        self.js_view = _code_view()

        self.preview_page = QWidget()
        self.web_view = _PreviewView(self) if QWebEngineView else QWidget()
        preview_layout = QVBoxLayout(self.preview_page)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        controls = QWidget()
        controls.setObjectName("previewControls")
        control_row = QHBoxLayout(controls)
        control_row.setContentsMargins(9, 7, 9, 7)
        self.preview_status = QLabel("No generated project")
        self.viewport = QComboBox()
        self.viewport.addItem("Desktop", 0)
        self.viewport.addItem("Tablet", 768)
        self.viewport.addItem("Mobile", 390)
        self.viewport.currentIndexChanged.connect(self._set_viewport)
        self.refresh_button = QPushButton("↻  Refresh")
        self.refresh_button.clicked.connect(self.refresh_preview)
        self.open_button = QPushButton("↗  Open separately")
        self.open_button.clicked.connect(self.open_separately)
        control_row.addWidget(self.preview_status, 1)
        control_row.addWidget(QLabel("Viewport"))
        control_row.addWidget(self.viewport)
        control_row.addWidget(self.refresh_button)
        control_row.addWidget(self.open_button)
        preview_layout.addWidget(controls)

        self.preview_stack = QStackedWidget()
        self.empty_state = QLabel("✳\n\nYour live preview will appear here\n\nDescribe an app and select Generate to create its frontend and backend.")
        self.empty_state.setObjectName("previewEmptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_state = QLabel("◌\n\nPreparing your project preview…")
        self.loading_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_state = QWidget()
        error_layout = QVBoxLayout(self.error_state)
        error_layout.addStretch()
        self.error_title = QLabel("Preview couldn’t start")
        self.error_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_detail = QLabel("Check that the generated project files are available.")
        self.error_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recover_button = QPushButton("Try again")
        self.recover_button.clicked.connect(self.refresh_preview)
        error_layout.addWidget(self.error_title)
        error_layout.addWidget(self.error_detail)
        error_layout.addWidget(self.recover_button, alignment=Qt.AlignmentFlag.AlignCenter)
        error_layout.addStretch()
        if QWebEngineView is not None:
            self.preview_stack.addWidget(self.empty_state)
            self.preview_stack.addWidget(self.loading_state)
            self.preview_stack.addWidget(self.error_state)
            self.preview_stack.addWidget(self.web_view)
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        else:
            fallback = QLabel(
                "The live preview needs PySide6 Addons. Install the desktop extras with:\n"
                "python -m pip install -e \".[ui]\"\n\n"
                "Then restart SketchForge to preview generated project files here."
            )
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setWordWrap(True)
            self.preview_stack.addWidget(fallback)
        preview_layout.addWidget(self.preview_stack, 1)
        runtime_bar = QWidget()
        runtime_layout = QHBoxLayout(runtime_bar)
        runtime_layout.setContentsMargins(8, 5, 8, 5)
        self.error_label = QLabel()
        self.error_label.setObjectName("runtimeError")
        self.runtime_recover = QPushButton("Reload")
        self.runtime_recover.clicked.connect(self.refresh_preview)
        runtime_layout.addWidget(self.error_label, 1)
        runtime_layout.addWidget(self.runtime_recover)
        runtime_bar.setVisible(False)
        self.runtime_bar = runtime_bar
        preview_layout.addWidget(runtime_bar)

        self.addTab(self.preview_page, "Preview")
        self.addTab(self.html_view, "HTML")
        self.addTab(self.css_view, "CSS")
        self.addTab(self.js_view, "JS")
        self.addTab(self.json_view, "Design IR")

    def attach_project(self, root: str | Path) -> None:
        """Show files from a materialised frontend project in the live preview."""
        project_root = Path(root).resolve()
        index = project_root / "home.html"
        if not index.is_file():
            index = project_root / "index.html"
        if not index.is_file():
            raise FileNotFoundError(f"No generated app entry point in {project_root}")
        self.project_root = project_root
        self._start_server()
        self._project_url = f"http://127.0.0.1:{self._server.server_port}/{index.name}"
        self.preview_status.setText(f"Live preview  ·  {project_root.name}")
        self.runtime_bar.setVisible(False)
        self._read_project_files()
        self.setCurrentIndex(0)
        self.refresh_preview()

    def _start_server(self) -> None:
        self._stop_server()
        assert self.project_root is not None
        handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
            *args, directory=str(self.project_root), **kwargs
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True, name="sketchforge-preview")
        server_thread.start()
        self._server, self._server_thread = server, server_thread

    def _stop_server(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _read_project_files(self) -> None:
        assert self.project_root is not None
        for view, path in ((self.html_view, self.project_root / "home.html"),
                           (self.css_view, self.project_root / "css" / "style.css"),
                           (self.js_view, self.project_root / "js" / "home.js")):
            if path.is_file():
                view.setPlainText(path.read_text(encoding="utf-8"))
        if self.controller.has_project:
            self.json_view.setPlainText(to_json(self.controller.document))

    def refresh(self) -> None:
        """Refresh source views from the sketch design when it changes."""
        if not self.controller.has_project:
            self.json_view.clear()
            return
        rendered = self.controller.render()
        if self.project_root is None:
            self.html_view.setPlainText(rendered.html)
            self.css_view.setPlainText(rendered.css)
            self.json_view.setPlainText(to_json(self.controller.document))

    def refresh_preview(self) -> None:
        if not self.project_root:
            self._show_state("empty")
            return
        if QWebEngineView is None:
            return
        self._show_state("starting")
        self.error_label.setVisible(False)
        self.web_view.setHtml(self._sandbox_document(self._project_url), QUrl("about:blank"))

    @staticmethod
    def _sandbox_document(project_url: str) -> str:
        safe_url = html.escape(project_url, quote=True)
        return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#101014}}iframe{{display:block;width:var(--frame-width,100%);height:100%;margin:0 auto;border:0;background:#111;box-shadow:0 0 0 1px #ffffff24}}
</style></head><body><iframe id="app" title="Generated app live preview" sandbox="allow-scripts allow-forms allow-modals allow-downloads" src="{safe_url}"></iframe>
<script>window.addEventListener('message',e=>{{if(e.data==='sketchforge-preview-error')document.title='SketchForge preview error'}});</script></body></html>'''

    def _show_state(self, state: str) -> None:
        if state == "empty":
            self.preview_stack.setCurrentWidget(self.empty_state)
        elif state == "starting":
            self.preview_stack.setCurrentWidget(self.loading_state)
        elif state == "error":
            self.preview_stack.setCurrentWidget(self.error_state)
        elif QWebEngineView is not None:
            self.preview_stack.setCurrentWidget(self.web_view)

    def _load_finished(self, ok: bool) -> None:
        if not ok:
            self.show_error("The preview renderer could not load the project files.", "Preview could not start")
            return
        self.preview_status.setText(f"●  Running locally  ·  {self.project_root.name if self.project_root else ''}")
        self._show_state("ready")
        self._set_viewport(self.viewport.currentIndex())

    def show_error(self, message: str, title: str = "Project generation failed") -> None:
        self.error_title.setText(title)
        self.error_detail.setText(message)
        self._show_state("error")

    def _set_viewport(self, _index: int) -> None:
        if QWebEngineView is None:
            return
        width = self.viewport.currentData()
        self.web_view.page().runJavaScript(
            f"document.getElementById('app').style.width='{width}px';"
            if width else "document.getElementById('app').style.width='100%';"
        )

    def open_separately(self) -> None:
        if not self._project_url or QWebEngineView is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("SketchForge · Live Preview")
        dialog.resize(1180, 820)
        layout = QVBoxLayout(dialog)
        view = _PreviewView(self)
        layout.addWidget(view)
        view.setHtml(self._sandbox_document(self._project_url), QUrl("about:blank"))
        dialog.exec()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._stop_server()
        super().closeEvent(event)

