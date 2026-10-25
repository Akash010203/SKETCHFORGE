# Prioritized Fix Plan: SketchForge Hybrid AI

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`  
**Status**: Actionable Engineering Plan (Awaiting user authorization before code edits)

---

## 1. Priority P0 — Eliminate Generation Discard & Stalling Bugs

### Objective
Guarantee that a user prompt reliably produces an AI-generated full-stack application, without discarding work or stalling on Stage 1.

| Issue | Target File & Function | Root Cause | Proposed Solution |
|---|---|---|---|
| **All-or-Nothing Discard** | `src/sketchforge/generation/ai_generator.py`: `ai_generate_project` | Missing 1 of 12 files causes `written != len(manifest)`, triggering `return None` and discarding all 10+ AI files. | **Per-file graceful fallback**: If Nemotron fails on an individual file (e.g. `projects.html`), fill that specific file from `project_planner` / templates. Deliver the hybrid AI project with 100% of files intact. |
| **`max_tokens` Cutoff on Large Code** | `src/sketchforge/generation/ai_generator.py`: `_FILE_SYSTEM`, `_stage2_file` | Forcing full code into `{"path": ..., "content": "..."}` JSON string exhausts tokens with escape characters. | Allow Nemotron to output code directly in standard markdown fences (````python ... ````) with higher token limits or chunking. |
| **Candidate Flapping on Stage 1** | `src/sketchforge/generation/ai_generator.py`: `_stage1_plan` | Rapid looping over candidates without delay or state persistence creates visual freezing in UI. | Pick active model using `pick_model()` once; expose transparent status (`"Connecting to <model>..."`); handle rate limits gracefully. |

---

## 2. Priority P1 — True Hybrid Data Contracts (Local AI $\leftrightarrow$ Nemotron)

### Objective
Ensure local OpenCV vision analysis and Design IR directly inform Nemotron's AppSpec planning and frontend generation.

| Task | Files Involved | Implementation Detail |
|---|---|---|
| **Structured Vision Injection** | `ui/web_studio.py`, `generation/ai_generator.py` | Replace crude percentage strings in `/api/sketch-analysis` with a validated `DesignDocument` summary (`assist/design_summary.py:summarize_design`). |
| **Geometry-Aware AppSpec** | `generation/app_specification.py`, `generation/ai_generator.py` | Feed detected component IDs, bounding boxes, and hierarchy into the Stage 1 AppSpec prompt. Nemotron preserves the detected spatial layout. |
| **Semantic Disambiguation** | `vision/component_detection.py`, `assist/model_planner.py` | When local detector flags a component as `ambiguous` (e.g. card vs container), ask Nemotron to resolve the semantic role. |

---

## 3. Priority P2 — Automated Verification & Visual Repair Loop

### Objective
Execute closed-loop visual and functional verification on generated applications.

```text
Generated Project
      │
      ▼
Start Local Sandbox (BackendServer + PreviewServer)
      │
      ▼
Capture Rendered Screenshot (verification/screenshot_capture.py)
      │
      ▼
Measure Visual Discrepancy against Source Sketch (evaluation/evaluator.py)
      │
      ▼
If Discrepancy > Threshold:
  Send Diff + Component ID to Nemotron for Targeted Patch
      │
      ▼
Re-verify and Accept or Rollback
```

1. **Screenshot Capture**: Trigger headless browser snapshot on the generated `/home.html`.
2. **Discrepancy Metric**: Compare component bounding boxes and colors in the rendered DOM against the source `DesignDocument`.
3. **Targeted Patch**: If an element is misaligned or missing, invoke `ai_revise_project()` with an automated, structured bug description.

---

## 4. Priority P3 — Unify Studio Control Plane

### Objective
Unify Web Studio (`web_studio.py`) and Desktop Workbench (`ui/main_window.py`) around one shared orchestration interface:
- Share `_JOBS` registry with real state machine (`queued`, `analyzing_sketch`, `planning_spec`, `generating_files`, `running_tests`, `comparing_visuals`, `completed`).
- Unify project storage under `output/projects/`.
- Provide consistent project export (ZIP, raw files, runnable scripts).
