"""Vision pipeline: image -> ink mask -> proposals -> classified detections -> hierarchy.

``analyze`` is the single in-process entry point the application controller and the workflow
orchestrator call. Each stage is also importable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sketchforge.bootstrap import VisionConfig
from sketchforge.utilities.timing import Stopwatch
from sketchforge.vision.component_detection import Detection, detect_components
from sketchforge.vision.image_loader import LoadedImage
from sketchforge.vision.layout_inference import LayoutInference, infer_hierarchy
from sketchforge.vision.normalization import NormalizedImage, normalize
from sketchforge.vision.perspective import PerspectiveResult, correct_perspective, map_point_to_source
from sketchforge.vision.preprocessing import PreprocessResult, preprocess
from sketchforge.vision.region_proposals import RegionProposals, build_proposals


@dataclass
class VisionResult:
    loaded: LoadedImage
    normalized: NormalizedImage
    preprocessed: PreprocessResult
    proposals: RegionProposals
    detections: list[Detection]
    inference: LayoutInference
    design_scale: float  # design pixels per working pixel
    perspective: PerspectiveResult
    timings_ms: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def to_source_scale(self) -> float:
        """Multiply working-pixel coordinates by this to get original-image pixels."""
        return 1.0 / self.normalized.scale

    def source_box(self, working_box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x, y, w, h = working_box
        points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        k = self.to_source_scale
        points = [(px * k, py * k) for px, py in points]
        if self.perspective.corrected and self.perspective.matrix is not None:
            points = [map_point_to_source(p, self.perspective.matrix) for p in points]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def choose_design_scale(frame_bbox: tuple[float, float, float, float], cfg: VisionConfig) -> float:
    _, _, fw, fh = frame_bbox
    target = cfg.design_width_landscape if fw >= fh else cfg.design_width_portrait
    return target / fw


def analyze(
    loaded: LoadedImage,
    cfg: VisionConfig | None = None,
    *,
    force_variant: str | None = None,
    close_kernel: int | None = None,
) -> VisionResult:
    cfg = cfg or VisionConfig()
    clock = Stopwatch()
    with clock.measure("perspective"):
        perspective = correct_perspective(loaded.bgr)
    with clock.measure("normalize"):
        norm = normalize(perspective.bgr, cfg.working_long_side)
    with clock.measure("preprocess"):
        pre = preprocess(norm, force_variant=force_variant, close_kernel=close_kernel)
    with clock.measure("proposals"):
        proposals = build_proposals(pre.ink, pre.stroke_width, cfg.min_component_side_px)
    scale = choose_design_scale(proposals.frame.bbox, cfg)
    with clock.measure("classify"):
        detections = detect_components(proposals, scale)
    with clock.measure("hierarchy"):
        inference = infer_hierarchy(detections)
    notes = [*perspective.notes, *pre.notes, *proposals.notes, *inference.notes]
    return VisionResult(
        loaded, norm, pre, proposals, detections, inference, scale, perspective, clock.as_dict(), notes
    )
