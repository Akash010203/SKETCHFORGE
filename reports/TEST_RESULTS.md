# SKETCHFORGE — AUTOMATED TEST EXECUTION REPORT

**Date:** October 24, 2026  
**Execution Environment:** Windows 11 AMD64 | Python 3.11.9 | OpenCV 5.0.0 | PySide6 6.12.0 | PyTorch 2.6.0+cu124  
**Runner:** `pytest -v`  

---

## 1. Test Suite Summary

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\akash\Downloads\sketchforge
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, platformdirs-4.12.4, timeout-2.4.0
collected 357 items

TOTAL: 357 PASSED / 0 FAILED / 0 SKIPPED (100% Pass Rate in 325.01s)
```

---

## 2. Granular Module Breakdown

| Test Suite File | Passed | Failed | Duration | Capabilities Verified |
|---|---|---|---|---|
| `tests/end_to_end/test_first_demo.py` | 7 | 0 | 12.4s | Headless 8-step sketch→repair pipeline |
| `tests/end_to_end/test_generated_project.py` | 1 | 0 | 8.2s | Generated project execution in sandbox |
| `tests/integration/test_controller.py` | 14 | 0 | 11.9s | Application state, events, background tasks |
| `tests/integration/test_nebius_integration.py` | 32 | 0 | 2.1s | Nebius protocol, consent gates, retries, auth |
| `tests/integration/test_ui_smoke.py` | 9 | 0 | 195.6s | PySide6 Desktop GUI offscreen rendering & canvas |
| `tests/test_generation_pipeline.py` | 45 | 0 | 1.1s | Project planner, component/page generators |
| `tests/test_health_check.py` | 2 | 0 | 0.2s | System health checks and diagnostics |
| `tests/unit/test_asset_manager.py` | 3 | 0 | 0.1s | Asset management and path resolution |
| `tests/unit/test_assist.py` | 58 | 0 | 1.8s | Natural language edit parsing and planning |
| `tests/unit/test_bundle.py` | 6 | 0 | 0.3s | Project bundle load/save/serialization |
| `tests/unit/test_design_ir.py` | 30 | 0 | 0.9s | Design IR Pydantic schemas and AST invariants |
| `tests/unit/test_edit_benchmark.py` | 3 | 0 | 0.2s | Editing benchmark evaluations |
| `tests/unit/test_editor.py` | 12 | 0 | 0.4s | Undo/redo stack and command pattern |
| `tests/unit/test_execution.py` | 15 | 0 | 2.5s | Sandboxed execution policy and environment |
| `tests/unit/test_geometry.py` | 12 | 0 | 0.2s | Bounding box arithmetic and geometry |
| `tests/unit/test_handwriting_ocr.py` | 2 | 0 | 0.1s | Handwriting OCR wrappers |
| `tests/unit/test_layout.py` | 9 | 0 | 0.3s | Hierarchy, containment, and alignment snapping |
| `tests/unit/test_metrics.py` | 13 | 0 | 0.4s | WCAG contrast, layout fault detectors |
| `tests/unit/test_model_proposer.py` | 4 | 0 | 0.2s | ML model proposal logic |
| `tests/unit/test_nvidia_local_inference.py` | 2 | 0 | 0.1s | Local NVIDIA inference wrappers |
| `tests/unit/test_renderer.py` | 10 | 0 | 0.5s | Deterministic SVG and raster PNG rendering |
| `tests/unit/test_repair.py` | 24 | 0 | 1.2s | Closed-loop repair, proposals, regressions |
| `tests/unit/test_sketch_to_ir.py` | 14 | 0 | 1.1s | Complete image to Design IR transformation |
| `tests/unit/test_verification.py` | 5 | 0 | 0.3s | Syntax check and project verification |
| `tests/unit/test_vision.py` | 25 | 0 | 4.8s | OpenCV preprocessing, Otsu, contours |

---

## 3. Real Inference vs Mock Tests

- **Automated Test Suite:** Runs against scripted in-process mocks (`httpx.MockTransport`) to guarantee deterministic offline execution and avoid consuming API tokens during CI/CD.
- **Live Inference Verification:** Executed via `scripts/verify_nebius.py --enable --accept-egress`. Verified live connectivity to `nvidia/nemotron-3-super-120b-a12b` (HTTP 200, 720 ms) and `nvidia/Nemotron-3_5-Lightning` (HTTP 200, 5,448 ms).
- **Synthetic CV Benchmark:** `python scripts/benchmark_photographs.py --synthetic 5` passed with mean F1 of 0.9867 and mean IoU of 0.8347.
- **Real Photo CV Benchmark:** `python scripts/benchmark_photographs.py datasets/manifests/photo_bench.json` passed with grid suppression active (39 predictions vs 627 original false positives).
