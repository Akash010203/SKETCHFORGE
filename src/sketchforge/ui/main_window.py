"""Main window: component tree and sketch on the left, canvas in the middle, inspector on the right."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
)

from sketchforge import __version__
from sketchforge.application.app_controller import AppController
from sketchforge.exceptions import SketchForgeError
from sketchforge.ui.bridge import ControllerBridge
from sketchforge.ui.component_tree import ComponentTree
from sketchforge.ui.correction_panel import CorrectionPanel
from sketchforge.ui.design_canvas import DesignCanvas
from sketchforge.ui.preview_panel import PreviewPanel
from sketchforge.ui.properties_panel import PropertiesPanel
from sketchforge.ui.sketch_import_view import SketchImportView
from sketchforge.ui.task_progress import TaskProgress

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.bridge = ControllerBridge(controller, self)
        self.resize(1480, 900)

        self.canvas = DesignCanvas(controller)
        self.tree = ComponentTree(controller)
        self.sketch_view = SketchImportView(controller)
        self.properties = PropertiesPanel(controller)
        self.correction = CorrectionPanel(controller)
        self.preview = PreviewPanel(controller)
        self.progress = TaskProgress()

        left = QTabWidget()
        left.addTab(self.tree, "Components")
        left.addTab(self.sketch_view, "Sketch")
        right = QTabWidget()
        right.addTab(self.properties, "Properties")
        right.addTab(self.correction, "Measure && repair")
        right.addTab(self.preview, "Code")
        self.left_tabs, self.right_tabs = left, right

        splitter = QSplitter(Qt.Orientation.Horizontal)
        for w in (left, self.canvas, right):
            splitter.addWidget(w)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 760, 420])
        self.setCentralWidget(splitter)
        self.statusBar().addPermanentWidget(self.progress)

        self._build_actions()
        self._wire()
        self._refresh_all()

    # ------------------------------------------------------------------ actions
    def _action(self, text: str, slot, shortcut: str | QKeySequence.StandardKey | None = None) -> QAction:
        act = QAction(text, self)
        act.triggered.connect(lambda _checked=False: slot())
        if shortcut is not None:
            act.setShortcut(QKeySequence(shortcut))
        return act

    def _build_actions(self) -> None:
        self.act_import = self._action("Import sketch…", self.choose_sketch, QKeySequence.StandardKey.Open)
        self.act_open = self._action("Open project…", self.choose_project)
        self.act_save = self._action("Save project", self.save_project, QKeySequence.StandardKey.Save)
        self.act_save_as = self._action("Save project as…", lambda: self.save_project(as_new=True))
        self.act_export = self._action("Export design…", self.export_design)
        self.act_quit = self._action("Quit", self.close, QKeySequence.StandardKey.Quit)
        self.act_undo = self._action("Undo", self.undo, QKeySequence.StandardKey.Undo)
        self.act_redo = self._action("Redo", self.redo, QKeySequence.StandardKey.Redo)
        self.act_fit = self._action("Fit to window", self.canvas.fit, "Ctrl+0")
        self.act_zoom_in = self._action("Zoom in", lambda: self.canvas.zoom(1.25), "Ctrl+=")
        self.act_zoom_out = self._action("Zoom out", lambda: self.canvas.zoom(0.8), "Ctrl+-")
        self.act_issues = QAction("Show issues on canvas", self, checkable=True, checked=True)
        self.act_issues.toggled.connect(self.canvas.set_show_issues)
        self.act_evaluate = self._action("Evaluate design", lambda: self._run(self.controller.evaluate), "Ctrl+E")
        self.act_repair = self._action("Auto-repair", self.correction._repair, "Ctrl+R")
        self.act_about = self._action("About", self.about)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.act_import)
        self.samples_menu = file_menu.addMenu("Open sample sketch")
        for path in self.controller.sample_sketches():
            act = QAction(path.stem.replace("_synthetic", "").replace("_", " "), self)
            act.triggered.connect(lambda _c=False, p=path: self.import_path(p))
            self.samples_menu.addAction(act)
        self.samples_menu.setEnabled(bool(self.controller.sample_sketches()))
        for act in (self.act_open, self.act_save, self.act_save_as, self.act_export):
            file_menu.addAction(act)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)
        edit = self.menuBar().addMenu("&Edit")
        edit.addActions([self.act_undo, self.act_redo])
        view = self.menuBar().addMenu("&View")
        view.addActions([self.act_fit, self.act_zoom_in, self.act_zoom_out])
        view.addSeparator()
        view.addAction(self.act_issues)
        tools = self.menuBar().addMenu("&Tools")
        tools.addActions([self.act_evaluate, self.act_repair])
        self.menuBar().addMenu("&Help").addAction(self.act_about)

        bar = self.addToolBar("Main")
        bar.setMovable(False)
        bar.addActions([self.act_import, self.act_save, self.act_undo, self.act_redo, self.act_fit,
                        self.act_evaluate, self.act_repair])

    def _wire(self) -> None:
        b = self.bridge
        b.project_opened.connect(self._on_project_opened)
        b.document_changed.connect(lambda *_: self._refresh_all())
        b.evaluation_changed.connect(lambda *_: self._on_evaluation())
        b.selection_changed.connect(lambda *_: self._on_selection())
        b.repair_started.connect(lambda: self.progress.start("repairing…"))
        b.repair_finished.connect(self._on_repair_finished)
        b.repair_event.connect(lambda name, data: self.progress.update_text(self._describe(name, data)))
        b.progress.connect(self.progress.update_text)
        b.error.connect(self._on_error)
        b.project_saved.connect(lambda p: self.statusBar().showMessage(f"saved to {p}", 5000))
        for source in (self.canvas, self.tree, self.correction):
            source.selection_requested.connect(self.controller.select)
        for source in (self.canvas, self.properties, self.correction):
            source.status_message.connect(lambda m: self.statusBar().showMessage(m, 8000))

    # ------------------------------------------------------------------ refresh
    def _refresh_all(self) -> None:
        self.canvas.reload()
        self.tree.rebuild()
        self.properties.refresh()
        self.correction.refresh()
        self.preview.refresh()
        self.sketch_view.refresh()
        self._update_actions()

    def _on_project_opened(self) -> None:
        self.canvas._fit_pending = True
        self.progress.finish("")
        self._refresh_all()
        self.setWindowTitle(self._title())
        project = self.controller.project
        n = len(self.controller.document.components) - 1
        self.statusBar().showMessage(f"{project.name}: {n} components", 6000)

    def _on_evaluation(self) -> None:
        self.canvas.refresh_overlays()
        self.tree.rebuild()
        self.correction.refresh()

    def _on_selection(self) -> None:
        self.canvas.refresh_overlays()
        self.tree.sync_selection()
        self.properties.refresh()

    def _on_repair_finished(self, report) -> None:
        self.progress.finish("")
        self.correction.on_repair_finished(report)
        self.right_tabs.setCurrentWidget(self.correction)
        self._refresh_all()

    def _on_error(self, message: str) -> None:
        self.progress.finish("")
        self.correction.on_repair_failed()
        self.statusBar().showMessage(message, 10000)

    @staticmethod
    def _describe(name: str, data: dict) -> str:
        return f"repair: {name} {data.get('issue', '')}".strip()

    def _title(self) -> str:
        if not self.controller.has_project:
            return f"SketchForge {__version__}"
        p = self.controller.project
        return f"{p.name}{' *' if p.dirty else ''} — SketchForge {__version__}"

    def _update_actions(self) -> None:
        has = self.controller.has_project
        stack = self.controller.project.stack if has else None
        self.act_undo.setEnabled(bool(stack and stack.can_undo))
        self.act_redo.setEnabled(bool(stack and stack.can_redo))
        if stack is not None:
            self.act_undo.setToolTip(f"Undo: {stack.undo_label()}" if stack.can_undo else "Nothing to undo")
            self.act_redo.setToolTip(f"Redo: {stack.redo_label()}" if stack.can_redo else "Nothing to redo")
        for act in (self.act_save, self.act_save_as, self.act_export, self.act_evaluate, self.act_repair, self.act_fit):
            act.setEnabled(has)
        self.setWindowTitle(self._title())

    # ------------------------------------------------------------------ user actions
    def _run(self, fn) -> None:
        try:
            fn()
        except SketchForgeError as exc:
            self.statusBar().showMessage(str(exc), 8000)

    def choose_sketch(self) -> None:
        start = str(self.controller.sample_sketches()[0].parent) if self.controller.sample_sketches() else ""
        path, _ = QFileDialog.getOpenFileName(self, "Import sketch", start, IMAGE_FILTER)
        if path:
            self.import_path(path)

    def import_path(self, path: str | Path) -> None:
        if not self.confirm_discard():
            return
        self.progress.start(f"importing {Path(path).name}…")
        self.controller.import_sketch_async(path)

    def choose_project(self) -> None:
        if not self.confirm_discard():
            return
        folder = QFileDialog.getExistingDirectory(self, "Open project folder")
        if folder:
            self._run(lambda: self.controller.open_project(folder))

    def save_project(self, as_new: bool = False) -> None:
        if not self.controller.has_project:
            return
        target = None if (as_new or self.controller.project.path is None) else self.controller.project.path
        if target is None:
            folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the project")
            if not folder:
                return
            target = Path(folder) / self.controller.project.name
        self._run(lambda: self.controller.save_project(target))
        self._update_actions()

    def export_design(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Export design to folder")
        if folder:
            self._run(lambda: self.statusBar().showMessage(
                f"exported {', '.join(sorted(self.controller.export(folder)))} to {folder}", 8000))

    def undo(self) -> None:
        self._run(self.controller.undo)

    def redo(self) -> None:
        self._run(self.controller.redo)

    def about(self) -> None:
        QMessageBox.about(
            self, "About SketchForge",
            f"SketchForge {__version__}\n\nA local-first workbench from sketch to measured, editable design.\n"
            "Everything runs on this computer; the application makes no network requests.")

    def confirm_discard(self) -> bool:
        """True when it is safe to replace the open project (override in tests)."""
        if not (self.controller.has_project and self.controller.project.dirty):
            return True
        answer = QMessageBox.question(
            self, "Unsaved changes", "Discard the unsaved changes to the open design?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self.confirm_discard():
            event.ignore()
            return
        self.bridge.detach()
        self.controller.close()
        event.accept()
