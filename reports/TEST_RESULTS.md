# Test Results & Verification Log

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`  
**Total Automated Tests**: 357 passing (0 failed, 0 skipped)

---

## 1. Automated Test Suite Execution Summary

| Test Module / Suite | Test Count | Execution Time | Status | Key Coverage Areas |
|---|---|---|---|---|
| `tests/integration/test_nebius_integration.py` | 32 | 3.73 s | **PASSED** | Outbound OpenAI client, retry backoff, privacy policies, consent gate, error translations. |
| `tests/end_to_end/test_first_demo.py` & `test_generated_project.py` | 8 | 23.07 s | **PASSED** | End-to-end sketch-to-repair pipeline, artifact generation, SQLite backend execution & CRUD tests in sandbox. |
| `tests/unit/test_vision.py` | 25 | 43.89 s | **PASSED** | Image validation, illumination flattening, contour/region detection, perspective correction, 105-sketch benchmark. |
| `tests/unit/test_repair.py` | 24 | 4.48 s | **PASSED** | 7 fault types (overflow, misalignment, spacing, text overflow, contrast, small control, overlap), regression check. |
| `tests/unit/test_metrics.py`, `test_layout.py`, `test_editor.py` | 34 | 0.73 s | **PASSED** | WCAG contrast, overflow, overlaps, layout snapping, undo/redo stack hash invariance. |
| `tests/unit/test_assist.py` | 58 | 0.88 s | **PASSED** | Natural language intent parsing, EditPlan schema, model planner, verified edit application. |
| `tests/unit/test_execution.py`, `test_verification.py`, `test_nvidia_local_inference.py` | 22 | 2.30 s | **PASSED** | Sandbox command policies, project inspection, test runners, local checkpoint loading. |
| `tests/unit/test_design_ir.py`, `test_renderer.py`, `test_sketch_to_ir.py` | 54 | 9.31 s | **PASSED** | DesignDocument serialization, migrations, SVG/HTML/CSS rendering, layout inference. |
| `tests/unit/test_bundle.py`, `test_asset_manager.py`, `test_geometry.py`, etc. | 30 | 2.50 s | **PASSED** | Single-file bundling, asset management, IoU/bounding box math, model proposer. |
| `tests/integration/test_controller.py`, `test_ui_smoke.py` | 23 | 193.45 s | **PASSED** | Offscreen Qt GUI events, tree selection, drag/resize canvas, undo/redo, auto-repair. |
| `tests/test_generation_pipeline.py` | 45 | 0.62 s | **PASSED** | React/TypeScript & HTML/CSS project planning, component/page/style generation, DDL/CRUD. |
| **Total Test Suite** | **357** | **~4.7 min** | **ALL PASSED** | **100% pass rate, 0 failures, 0 skips.** |

---

## 2. Live Network & Model Verification

### A. Nebius Token Factory Probe (`scripts/verify_nebius.py`)
- **Command**: `python scripts/verify_nebius.py --enable --accept-egress`
- **Result**: **SUCCESS**
- **Endpoint**: `https://api.tokenfactory.nebius.com/v1/`
- **Model Verified**: `nvidia/Nemotron-3_5-Lightning`
- **Roundtrip Latency**: 750.7 ms
- **Models Enumerated**: 30 total (5 NVIDIA models: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/Nemotron-3.5-Super-VL`, `nvidia/Nemotron-3_5-Lightning`, `nvidia/nemotron-3-super-120b-a12b`).

### B. Live Two-Stage Project Generation (`ai_generator.py`)
- **Stage 1 (AppSpec Plan)**: **SUCCESS**
  - Model: `nvidia/nemotron-3-super-120b-a12b`
  - Output: AppSpec with name `'CounterApp'`, 1 page, 1 entity.
- **Stage 2 (File Generation)**: **PARTIAL FAILURE & DISCARD**
  - 10 of 12 files generated successfully.
  - `projects.html` failed: empty answer.
  - `backend/api.py` failed: max_tokens cutoff.
  - Entire generated project discarded due to all-or-nothing check.
