"""Merge shape, line and text observations into page-aware proposals.

Decides what the page itself is (a drawn frame, or the ink extent), removes emergent regions that
nobody drew (the "page body" left between a header and the frame), and separates real dividers
from the edges of rectangles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sketchforge.vision.contour_detection import Box, ShapeObservation, detect_shapes
from sketchforge.vision.line_detection import LineObservation, detect_lines
from sketchforge.vision.text_regions import TextRegion, find_text_regions


@dataclass
class PageFrame:
    bbox: Box
    source: str  # 'drawn_frame' | 'ink_extent'
    shape: ShapeObservation | None = None


@dataclass
class RegionProposals:
    frame: PageFrame
    shapes: list[ShapeObservation]  # excludes the frame
    dividers: list[LineObservation]
    texts: list[TextRegion]
    stroke_width: float
    notes: list[str] = field(default_factory=list)


def _edges(box: Box) -> dict[str, float]:
    x, y, w, h = box
    return {"left": x, "right": x + w, "top": y, "bottom": y + h}


def _touches(box: Box, frame: Box, tol: float) -> int:
    be, fe = _edges(box), _edges(frame)
    return sum(abs(be[k] - fe[k]) <= tol for k in be)


def _center_inside(box: Box, outer: Box) -> bool:
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    return outer[0] <= cx <= outer[0] + outer[2] and outer[1] <= cy <= outer[1] + outer[3]


def _line_is_shape_edge(line: LineObservation, shapes: list[ShapeObservation], tol: float) -> bool:
    for s in shapes:
        x, y, w, h = s.bbox
        if line.orientation == "h":
            coord = (line.y1 + line.y2) / 2
            lo, hi = sorted((line.x1, line.x2))
            for edge_y, (e_lo, e_hi) in ((y, (x, x + w)), (y + h, (x, x + w))):
                if abs(coord - edge_y) <= tol:
                    overlap = min(hi, e_hi) - max(lo, e_lo)
                    if overlap >= 0.6 * min(hi - lo, e_hi - e_lo):
                        return True
        else:
            coord = (line.x1 + line.x2) / 2
            lo, hi = sorted((line.y1, line.y2))
            for edge_x, (e_lo, e_hi) in ((x, (y, y + h)), (x + w, (y, y + h))):
                if abs(coord - edge_x) <= tol:
                    overlap = min(hi, e_hi) - max(lo, e_lo)
                    if overlap >= 0.6 * min(hi - lo, e_hi - e_lo):
                        return True
    return False


def build_proposals(ink: np.ndarray, stroke_width: float, min_side: int = 10) -> RegionProposals:
    notes: list[str] = []
    h_img, w_img = ink.shape
    all_shapes = detect_shapes(ink, stroke_width, min_side=min_side)

    # --- the page frame ---------------------------------------------------------------------
    frame_shape: ShapeObservation | None = None
    big = [
        s for s in all_shapes
        if s.kind in ("rect", "rounded_rect") and s.area >= 0.30 * ink.size
    ]
    if big:
        frame_shape = max(big, key=lambda s: s.area)
    if frame_shape is not None:
        frame = PageFrame(frame_shape.bbox, "drawn_frame", frame_shape)
    else:
        ys, xs = np.nonzero(ink)
        pad_x, pad_y = 0.03 * w_img, 0.03 * h_img
        x0, y0 = max(0.0, xs.min() - pad_x), max(0.0, ys.min() - pad_y)
        x1, y1 = min(float(w_img), xs.max() + pad_x), min(float(h_img), ys.max() + pad_y)
        frame = PageFrame((float(x0), float(y0), float(x1 - x0), float(y1 - y0)), "ink_extent")
        notes.append("no page outline found; page area taken from the extent of the drawing")

    # --- drop emergent / out-of-frame shapes -----------------------------------------------
    tol = max(2.0 * stroke_width, 8.0)
    fx, fy, fw, fh = frame.bbox
    shapes: list[ShapeObservation] = []
    for s in all_shapes:
        if s is frame_shape:
            continue
        if not _center_inside(s.bbox, frame.bbox):
            notes.append(f"ignored a shape outside the page frame at {tuple(round(v) for v in s.bbox)}")
            continue
        if frame_shape is not None and s.area >= 0.58 * frame_shape.area and _touches(s.bbox, frame.bbox, tol) >= 2:
            notes.append("ignored the leftover 'page body' region (not drawn as its own box)")
            continue
        shapes.append(s)

    # --- dividers: straight strokes that are not the edge of a box --------------------------
    min_len = max(40, round(0.07 * max(w_img, h_img)))
    all_lines = detect_lines(ink, stroke_width, min_length=min_len)
    edge_shapes = ([frame_shape] if frame_shape else []) + shapes
    edge_tol = 1.5 * stroke_width + 3
    dividers = [
        ln for ln in all_lines
        if _center_inside(ln.bbox, frame.bbox)
        and not _line_is_shape_edge(ln, edge_shapes, edge_tol)
    ]
    for i, ln in enumerate(dividers):
        ln.uid = i

    # --- text -------------------------------------------------------------------------------
    erase_shapes = ([frame_shape] if frame_shape else []) + shapes
    texts = [
        t for t in find_text_regions(ink, erase_shapes, all_lines, stroke_width)
        if _center_inside(t.bbox, frame.bbox)
    ]
    for i, t in enumerate(texts):
        t.uid = i
    return RegionProposals(frame, shapes, dividers, texts, stroke_width, notes)
