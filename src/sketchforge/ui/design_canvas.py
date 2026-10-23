"""The design canvas: the rendered SVG with selection, drag-to-move, resize and issue overlays.

The canvas draws the *same SVG* the exporter writes, so what you edit is what you export. Mouse
actions become controller commands only on release (one undo step per drag).
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView

from sketchforge.application.app_controller import AppController
from sketchforge.design_ir.schema import Component
from sketchforge.editor.selection import hit_test
from sketchforge.exceptions import SketchForgeError

HANDLE = 10.0  # resize handle edge in design px
DRAG_THRESHOLD = 3.0
SEVERITY_COLOR = {"error": "#dc2626", "warning": "#d97706", "info": "#2563eb"}


class DesignCanvas(QGraphicsView):
    status_message = Signal(str)
    selection_requested = Signal(object)  # list of ids

    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor("#e2e8f0")))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self._renderer: QSvgRenderer | None = None
        self._svg_item: QGraphicsSvgItem | None = None
        self._overlays: list[QGraphicsRectItem] = []
        self._show_issues = True
        self._fit_pending = True
        self._drag: dict | None = None
        self._ghost: QGraphicsRectItem | None = None

    # ------------------------------------------------------------------ public
    def set_show_issues(self, on: bool) -> None:
        self._show_issues = on
        self.refresh_overlays()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802 (Qt API)
        """Paint the dark dotted studio board behind the editable design."""
        painter.fillRect(rect, QColor("#101014"))
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#31303a"))
        spacing = 24
        x0 = int(rect.left() // spacing) * spacing
        y0 = int(rect.top() // spacing) * spacing
        x1, y1 = int(rect.right()) + spacing, int(rect.bottom()) + spacing
        for x in range(x0, x1, spacing):
            for y in range(y0, y1, spacing):
                painter.drawEllipse(QPointF(x, y), 1.0, 1.0)
        painter.restore()

    def reload(self) -> None:
        """Re-render the current document (call after any document change)."""
        scene = self.scene()
        if not self.controller.has_project:
            scene.clear()
            self._svg_item, self._renderer, self._overlays, self._ghost = None, None, [], None
            return
        rendered = self.controller.render()
        self._renderer = QSvgRenderer(QByteArray(rendered.svg.encode("utf-8")), self)
        if self._svg_item is None or self._svg_item.scene() is not scene:
            scene.clear()
            self._overlays, self._ghost = [], None
            self._svg_item = QGraphicsSvgItem()
            self._svg_item.setZValue(0)
            scene.addItem(self._svg_item)
        self._svg_item.setSharedRenderer(self._renderer)
        page = self.controller.document.page
        self._svg_item.setScale(page.width / max(self._renderer.defaultSize().width(), 1))
        scene.setSceneRect(QRectF(-40, -40, page.width + 80, page.height + 80))
        self.refresh_overlays()
        if self._fit_pending:
            self.fit()
            self._fit_pending = False

    def fit(self) -> None:
        if self._svg_item is not None:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        self.scale(factor, factor)

    def refresh_overlays(self) -> None:
        scene = self.scene()
        for item in self._overlays:
            scene.removeItem(item)
        self._overlays = []
        if not self.controller.has_project:
            return
        doc = self.controller.document
        project = self.controller.project
        if self._show_issues and project.evaluation is not None:
            for issue in project.evaluation.issues:
                for cid in issue.component_ids:
                    comp = doc.get(cid)
                    if comp is not None:
                        self._add_rect(comp.bbox, SEVERITY_COLOR[issue.severity], dashed=True, width=1.6, z=5)
        for cid in project.selection.ids:
            comp = doc.get(cid)
            if comp is not None:
                self._add_rect(comp.bbox, "#2563eb", width=2.0, z=10)
                if cid == project.selection.primary:
                    b = comp.bbox
                    handle = QGraphicsRectItem(b.x2 - HANDLE / 2, b.y2 - HANDLE / 2, HANDLE, HANDLE)
                    handle.setBrush(QBrush(QColor("#ffffff")))
                    handle.setPen(QPen(QColor("#2563eb"), 1.5))
                    handle.setZValue(11)
                    scene.addItem(handle)
                    self._overlays.append(handle)

    def _add_rect(self, b, color: str, *, dashed: bool = False, width: float = 1.5, z: float = 5) -> QGraphicsRectItem:
        item = QGraphicsRectItem(b.x, b.y, b.w, b.h)
        pen = QPen(QColor(color), width)
        pen.setCosmetic(True)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        item.setPen(pen)
        item.setZValue(z)
        self.scene().addItem(item)
        self._overlays.append(item)
        return item

    # ------------------------------------------------------------------ mouse
    def _on_handle(self, comp: Component, pos: QPointF) -> bool:
        b = comp.bbox
        tol = max(HANDLE, 8.0 / max(self.transform().m11(), 1e-6))
        return abs(pos.x() - b.x2) <= tol and abs(pos.y() - b.y2) <= tol

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() != Qt.MouseButton.LeftButton or not self.controller.has_project:
            return super().mousePressEvent(event)
        pos = self.mapToScene(event.position().toPoint())
        doc = self.controller.document
        primary = self.controller.project.selection.primary
        current = doc.get(primary) if primary else None
        if current is not None and self._on_handle(current, pos):
            self._drag = {"mode": "resize", "id": current.id, "start": pos, "box": current.bbox, "moved": False}
            return
        hit = hit_test(doc, pos.x(), pos.y())
        if hit is None:
            self.selection_requested.emit([])
            return
        if hit.id != primary:
            self.selection_requested.emit([hit.id])
        self._drag = {"mode": "move", "id": hit.id, "start": pos, "box": hit.bbox, "moved": False}

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            return super().mouseMoveEvent(event)
        pos = self.mapToScene(event.position().toPoint())
        d = self._drag
        dx, dy = pos.x() - d["start"].x(), pos.y() - d["start"].y()
        if not d["moved"] and (dx * dx + dy * dy) ** 0.5 < DRAG_THRESHOLD:
            return
        d["moved"] = True
        b = d["box"]
        if d["mode"] == "move":
            rect = QRectF(b.x + dx, b.y + dy, b.w, b.h)
        else:
            rect = QRectF(b.x, b.y, max(b.w + dx, 4.0), max(b.h + dy, 4.0))
        if self._ghost is None:
            self._ghost = QGraphicsRectItem()
            pen = QPen(QColor("#2563eb"), 1.5, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._ghost.setPen(pen)
            self._ghost.setBrush(QBrush(QColor(37, 99, 235, 40)))
            self._ghost.setZValue(20)
            self.scene().addItem(self._ghost)
        self._ghost.setRect(rect)
        d["delta"] = (dx, dy)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        d, self._drag = self._drag, None
        if self._ghost is not None:
            self.scene().removeItem(self._ghost)
            self._ghost = None
        if d is None or not d["moved"]:
            return super().mouseReleaseEvent(event)
        dx, dy = d["delta"]
        try:
            if d["mode"] == "move":
                self.controller.move_component(d["id"], round(dx, 1), round(dy, 1))
            else:
                b = d["box"]
                self.controller.resize_component(d["id"], round(max(b.w + dx, 4.0), 1), round(max(b.h + dy, 4.0), 1))
        except SketchForgeError as exc:
            self.status_message.emit(str(exc))
            self.refresh_overlays()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit_pending is False and self._svg_item is not None and self.transform().isIdentity():
            self.fit()
