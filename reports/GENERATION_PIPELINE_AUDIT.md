# Generation Pipeline Audit

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`  
**Status**: Confirmed Architectural Defects & Pipeline Failure Analysis

---

## 1. Overview of Generation Modules

| Module | Purpose | Status |
|---|---|---|
| `generation/app_specification.py` | Defines `AppSpec`, `PageSpec`, `FieldSpec`, `EntitySpec`, `ActionSpec`. Bridges Design IR to full-stack specs. | Solid dataclass foundation; heuristic converter `spec_from_document()` exists. |
| `generation/project_planner.py` | Plans full React/TypeScript (`plan_react_ts`) and HTML/CSS (`plan_html_css`) file trees from `AppSpec`. | Fully tested (45 tests passing). |
| `generation/studio_generator.py` | Orchestrates project materialization. Tries AI generation first; falls back to static template generator. | High-level coordinator; lacks resilience and granular recovery. |
| `generation/ai_generator.py` | 2-stage prompt sequence with Nemotron: Stage 1 = AppSpec plan; Stage 2 = 12 individual file calls. | Primary failure point identified. |
| `generation/vite_react_studio.py` | Complete Vite + React + TypeScript + SQLite scaffold generator. | Complete and functional template generator. |
| `generation/backend_server.py` | Ephemeral subprocess runner for generated Flask API with `X-Studio-Token` auth. | Functional process supervisor. |

---

## 2. Root Cause Analysis: The Fatal Flaws in `ai_generator.py`

### Flaw 1: Compounding Sequential Probability Failure
In `ai_generator.py`, Stage 2 iterates through a fixed list of 12 files:
`index.html`, `css/style.css`, `home.html`, `projects.html`, `js/home.js`, `js/projects.js`, `backend/schema.sql`, `backend/models.py`, `backend/database.py`, `backend/logic.py`, `backend/api.py`, `requirements.txt`.

Each file is generated via an independent HTTP completion call to Nemotron.
If the probability of any single model completion succeeding within token limits is $90\%$, the probability of all 12 succeeding consecutively is:
$$P(\text{all } 12 \text{ succeed}) = 0.90^{12} \approx 28.2\%$$
There is an **over 70% probability** that at least one file generation will fail or hit a limit!

### Flaw 2: All-or-Nothing Discard Policy
Lines 209–214 in `src/sketchforge/generation/ai_generator.py`:
```python
if written != len(manifest):
    missing = len(manifest) - written
    _emit(f"AI generation was incomplete ({written}/{len(manifest)} files); "
          f"using the complete template generator instead.")
    log.warning("Discarding incomplete AI project %s (%d file(s) missing).", root, missing)
    return None
```
When our test ran, 10 out of 12 files were generated successfully with high quality. However, because `projects.html` and `backend/api.py` failed, the pipeline completely deleted all 10 AI-generated files and returned `None`.

### Flaw 3: `max_tokens` Cutoff on Complex Files
In `_stage2_file()`, `backend/api.py` failed with:
`the answer was cut off (max_tokens reached); it would not be valid JSON`
Because `_FILE_SYSTEM` instructs the model to return `{"path": "...", "content": "..."}`, Nemotron attempts to escape the entire Python file inside a JSON string. Long files easily exhaust token boundaries, truncating the JSON and failing the parser.

### Flaw 4: Empty Model Responses on Certain Slugs
`projects.html` failed with:
`the service returned an empty answer`
In reasoning models or models with internal think blocks, token budgets are sometimes consumed before the message content is emitted, or `finish_reason` stops before text generation begins.

### Flaw 5: Disconnect Between Local Vision and Generation
When a user uploads a sketch in Web Studio, `/api/sketch-analysis` runs OpenCV, but converts the rich detection data into a crude string of bullet points:
```text
button at (24%, 45%), about 15% wide by 5% tall
```
This string is prepended to the user prompt. The pipeline does **not**:
- Construct a true `DesignDocument` from the uploaded image.
- Map component bounding boxes into the `AppSpec`.
- Use local OpenCV layout measurements or color extraction in the frontend code generator.
- Compare rendered screenshots back against the sketch.

---

## 3. Discrepancy & Verification Loop Gaps

Although `tests/unit/test_verification.py` and `execution/docker_sandbox.py` exist:
- The Web Studio does **not** run automated screenshot capture after generating an application.
- The local evaluator (`evaluation/evaluator.py`) is never invoked on the generated HTML/CSS output.
- No visual discrepancy comparison is executed between the source sketch and the rendered application preview.
