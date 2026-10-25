# AI System Inventory: Local Capabilities & Models

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`  
**Status**: Verified through code inspection and benchmark execution

---

## 1. Overview of "My Own AI System"

SketchForge possesses an extensive, highly engineered suite of deterministic computer vision algorithms, layout inference heuristics, geometric measurement tools, and local machine learning models.

```text
Input Sketch
    │
    ▼
[vision/image_loader.py] ──> Validation (size, type, pixel budget)
    │
    ▼
[vision/preprocessing.py] ──> Illumination flattening, morphological closing, adaptive thresholding
    │
    ▼
[vision/region_proposals.py] ──> Contour analysis, minimum area filtering, hierarchy nesting
    │
    ▼
[vision/component_detection.py] ──> Geometric & topological classification rules
    │
    ▼
[layout/design_refinement.py] ──> Snapping, containment enforcement, spacing pitch
    │
    ▼
[design_ir/schema.py] ──> Strict DesignDocument IR with lossless undo/redo
    │
    ▼
[evaluation/evaluator.py] ──> 10 visual & layout issue codes (WCAG contrast, overflow, overlaps)
    │
    ▼
[repair/repair_rules.py] ──> Closed-loop minimal translation/resizing patches
```

---

## 2. Detailed Subsystem Inventory

### A. Computer Vision & Image Preprocessing (`src/sketchforge/vision/`)

| Module | Core Functionality | Verified Status |
|---|---|---|
| `image_loader.py` | Magic bytes check, format validation (PNG, JPEG), bounds & pixel budget enforcement (max 25 MP). | Tested & Verified (`tests/unit/test_vision.py`) |
| `preprocessing.py` | Flatten illumination via large-kernel Gaussian/box morphological filters; Otsu and adaptive Gaussian thresholding; stroke width estimation via distance transforms. | Tested & Verified |
| `perspective.py` | 4-point quadrilateral detection and perspective warp rectification for tilted sketches. | Tested & Verified |
| `contour_detection.py` | OpenCV contour retrieval, polygon approximation (`cv2.approxPolyDP`), bounding rects. | Tested & Verified |
| `region_proposals.py` | Filters noise contours, groups bounding boxes, deduces page boundary frame. | Tested & Verified |
| `component_detection.py` | Rule-based classifier assigning component types (`button`, `input`, `card`, `heading`, `text`, `image`, `checkbox`, `divider`) with confidence and ambiguity scores. | Verified on synthetic layouts (F1: 0.982) |
| `handwriting_ocr.py` | Optional handwriting recognition hook (Microsoft TrOCR or local CRNN-CTC). Off by default. | Tested & Functional |

### B. Layout Engine & Design IR (`src/sketchforge/layout/`, `design_ir/`)

| Module | Core Functionality | Verified Status |
|---|---|---|
| `design_ir/schema.py` | Formal Pydantic/dataclass schema for `DesignDocument`, `Component`, `BBox`, `Color`. | Fully Tested (`tests/unit/test_design_ir.py`) |
| `layout/hierarchy.py` | Builds tree containment based on bounding box geometry and area overlap. | Tested & Verified |
| `layout/design_refinement.py` | Snaps alignment edges (left, center, right), uniform vertical pitch, and clamps out-of-bounds items. | Tested & Verified |
| `editor/undo_redo.py` | In-memory atomic undo/redo command stack with exact hash equivalence. | Tested & Verified |

### C. Layout Evaluation & Visual Repair Engine (`src/sketchforge/evaluation/`, `repair/`)

| Module | Issue Codes Handled | Verified Matrix |
|---|---|---|
| `evaluation/evaluator.py` | 10 issue codes: `overflow`, `page_overflow`, `misalignment`, `spacing`, `overlap`, `text_overflow`, `low_contrast`, `small_control`, `small_font`, `fidelity_mismatch`. | 100% verified (`tests/unit/test_metrics.py`) |
| `repair/repair_rules.py` | Proposes minimal deterministic translations, resizings, and color corrections. | 337-cell fault injection matrix: 97.0% repaired, 0% regressed |
| `repair/regression_check.py` | Accepts patch only if target fault score improves and no new/worsened issues are introduced. | Verified (`tests/unit/test_repair.py`) |

### D. Local Trained Models & Checkpoints (`checkpoints/`, `src/sketchforge/models/`)

| Component | Architecture | Weights Location | Current Status |
|---|---|---|---|
| Component Detector | Compact CNN + Feature Pyramid / Anchor Decoder | `checkpoints/component_detector_v1/best.pt` | Checkpoint exists (`best.pt`, 2.5 MB). Note from `TASKS.md`: trained for 5-10 epochs on synthetic layouts; IoU/mAP benchmark remains 0. Currently unused by main inference pipeline (rule-based detector is primary). |
| Layout Model | Compact Semantic Segmentation | `src/sketchforge/models/layout_model/` | Code structure implemented; no trained checkpoint exists. |
| Handwriting OCR | CRNN-CTC / TrOCR | `checkpoints/handwriting_ocr.pt` (optional) | Code implemented in `models/handwriting_ocr.py`; opt-in via environment variable `SKETCHFORGE_OCR_MODEL`. |

---

## 3. Ground Truth vs Synthetic Limitations

- **Synthetic Benchmark**: The local detector achieves F1 0.982, type accuracy 0.946, and mean IoU 0.835 on *synthetically generated* clean sketches (`assets/sample_sketches/`).
- **Real-World Photos**: On real photographed grid-paper sketches, the rule-based OpenCV detector currently yields F1 0.0031 and type accuracy 0.0000 (`experiments/results/real_photo_benchmark.json`). Grid lines and uneven lighting confuse contour detection.
- **Independence**: The local system is 100% operational offline without any network access or external credentials.
