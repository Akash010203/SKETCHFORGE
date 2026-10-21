"""Preprocessing: choose a binarization variant and produce a clean ink mask.

Several thresholding variants are tried and scored; the best-scoring one is used. The score is a
transparent heuristic (plausible ink coverage, little speckle), recorded in the result so the
choice can be inspected and ablated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from sketchforge.exceptions import PreprocessingError
from sketchforge.vision.morphology import (
    close_gaps,
    estimate_stroke_width,
    remove_small_components,
    speckle_fraction,
)
from sketchforge.vision.normalization import NormalizedImage
from sketchforge.vision.thresholding import VARIANTS

TARGET_INK_RATIO = 0.025  # typical share of a page covered by pen strokes in a wireframe


@dataclass
class PreprocessResult:
    ink: np.ndarray  # uint8 mask, 255 = ink, gaps bridged, specks removed
    variant: str
    variant_scores: dict[str, float]
    stroke_width: float  # working pixels
    ink_ratio: float
    notes: list[str] = field(default_factory=list)


def score_variant(mask: np.ndarray) -> float:
    """Higher is better. Penalizes implausible ink coverage and speckle."""
    ratio = float(np.count_nonzero(mask)) / mask.size
    if ratio <= 0:
        return -10.0
    coverage_penalty = abs(math.log(ratio / TARGET_INK_RATIO))
    if ratio > 0.25:
        coverage_penalty += 3.0  # almost certainly a bad threshold (paper counted as ink)
    return -coverage_penalty - 2.0 * speckle_fraction(mask)


def suppress_ruled_lines(mask: np.ndarray) -> tuple[np.ndarray, str | None]:
    """Remove long, regularly spaced paper rules from a binary ink mask.

    Suppression is deliberately gated on a repeated pattern. A single long box edge must not
    be mistaken for notebook ruling. The detected line pixels are removed without eroding
    neighboring strokes, which helps preserve handwriting that crosses a rule.
    """
    h, w = mask.shape
    detected = np.zeros_like(mask)
    directions: list[str] = []
    for orientation, length in (("horizontal", w), ("vertical", h)):
        kernel_len = max(25, length // 24)
        kernel_shape = (kernel_len, 1) if orientation == "horizontal" else (1, kernel_len)
        opened = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel_shape)
        )
        profile = (opened > 0).sum(axis=1 if orientation == "horizontal" else 0)
        threshold = max(12, int(round(0.22 * length)))
        indices = np.flatnonzero(profile >= threshold)
        if indices.size < 5:
            continue
        gaps = np.diff(indices)
        # Group adjacent rows/columns into individual rules before checking spacing.
        groups = np.split(indices, np.flatnonzero(gaps > 2) + 1)
        centers = np.array([float(group.mean()) for group in groups if group.size])
        if centers.size < 5:
            continue
        spacings = np.diff(centers)
        median_spacing = float(np.median(spacings))
        if (median_spacing < 4 or median_spacing > 0.12 * length
                or float(np.median(np.abs(spacings - median_spacing))) / median_spacing > 0.35):
            continue
        detected = cv2.bitwise_or(detected, opened)
        directions.append(orientation)

    if not directions:
        return mask, None
    filtered = cv2.bitwise_and(mask, cv2.bitwise_not(detected))
    return filtered, f"suppressed repeated {' and '.join(directions)} ruled-paper lines"


def preprocess(
    norm: NormalizedImage,
    force_variant: str | None = None,
    close_kernel: int | None = None,
) -> PreprocessResult:
    if force_variant is not None and force_variant not in VARIANTS:
        raise PreprocessingError(f"unknown threshold variant {force_variant!r}")
    candidates = {name: fn(norm.gray) for name, fn in VARIANTS.items()}
    scores = {name: round(score_variant(mask), 4) for name, mask in candidates.items()}
    chosen = force_variant or max(scores, key=lambda k: scores[k])
    raw = candidates[chosen]

    notes: list[str] = []
    raw, grid_note = suppress_ruled_lines(raw)
    if grid_note:
        notes.append(grid_note)
    despeckled = remove_small_components(raw, min_area=10)
    stroke_width = estimate_stroke_width(despeckled)
    # Bridge only the 1-3 px gaps left at hand-drawn corners. A larger kernel would fill the
    # triangles of an X-marked image box and the inside of small checkboxes.
    kernel = close_kernel if close_kernel is not None else max(3, round(0.5 * stroke_width) | 1)
    closed = close_gaps(despeckled, kernel)
    ink = remove_small_components(closed, min_area=max(12, int(2.5 * stroke_width)))

    ratio = float(np.count_nonzero(ink)) / ink.size
    if ratio < 0.0008:
        raise PreprocessingError(
            "almost no ink was found; the sketch may be blank, too faint, or too small"
        )
    if ratio > 0.40:
        raise PreprocessingError(
            "the image is mostly dark after thresholding; the photo may be underexposed or "
            "the background is not a light sheet of paper"
        )
    if ratio > 0.2:
        notes.append(f"high ink coverage ({ratio:.0%}); detection quality may be poor")
    return PreprocessResult(
        ink=ink,
        variant=chosen,
        variant_scores=scores,
        stroke_width=stroke_width,
        ink_ratio=ratio,
        notes=notes,
    )


def to_gray_u8(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
