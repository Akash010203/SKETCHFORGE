# File structure: what exists, what is planned, where it deviates

Responsibilities follow the original specification. Only modules whose milestone has started
exist; the rest are listed under *Planned* and are deliberately **not** created as empty files.

## Implemented

| Path | Responsibility |
|---|---|
| `src/sketchforge/__main__.py`, `app.py` | CLI (`demo`, `gui`, `info`) and GUI bootstrap (Qt imported lazily) |
| `bootstrap.py`, `constants.py`, `exceptions.py`, `logging_setup.py` | typed config (defaults + `config/*.yaml`), shared constants, exception hierarchy |
| `design_ir/` | schema (pydantic v2), document/tree ops, geometry, constraints & regression policy, validation, serialization, migrations |
| `vision/` | image loading, normalization, thresholding, morphology, preprocessing, line/contour/text detection, region proposals, classification, hierarchy, confidence, visualization, pipeline |
| `layout/` | grouping (alignment families, repeated groups), alignment, spacing, overlap/sliver trimming, `design_refinement.build_document` (detections → IR) |
| `domain/` | `typography` (text width model, placeholders), `color_system` (WCAG contrast) |
| `rendering/` | SVG, HTML, CSS, raster snapshot, theme engine, facade (`renderer.render_all`) |
| `editor/` | undoable commands, undo stack, selection/hit-testing, property editing, layer ordering, change history |
| `evaluation/` | issue vocabulary, layout/geometry/text/image metrics, evaluator, report, detection metrics + benchmark runner |
| `repair/` | issue detector, diagnosis, rules, planner, patch, regression check, rollback, error injection |
| `orchestration/` | step registry, workflow runner/state/history, retry policy, budget, stopping rules, sketch + repair workflows |
| `application/` | `AppController`, `EventBus`, `TaskManager`, project manager, import/export |
| `storage/` | project folder format (`project.json`, `design.json`, source, renders, reports) |
| `datasets/synthetic_generator.py` | original sketch generator with exact ground truth (wobbly strokes, shadows, noise) |
| `ui/` | main window, canvas, component tree, properties, measure & repair, code preview, sketch view, task progress, controller→Qt bridge |
| `utilities/` | paths (atomic writes), hashing, timing |
| `integrations/` | `provider_interface` (typed contract + error family), `nebius/` (Token Factory client: consent gate, privacy limits, bounded retries, usage log, model registry, health check), `nvidia/` (model catalogue). The only package that talks to the network |
| `assist/` | natural-language edits (Phase 7): `edit_plan` (typed allowlisted ops, validation, atomic undoable command), `design_summary` (privacy-aware summary), `local_parser` (rule-based baseline), `model_planner` (strict-JSON planner over any provider), `verified_edit` (apply on a copy, evaluate, repair only what the edit broke) |
| `scripts/` | `inspect_environment`, `inspect_storage`, `make_sample_sketches`, `evaluate_layout`, `evaluate_repair`, `bundle_project` (whole project in one file, round-trip tested) |
| `tests/` | `unit/` (11 files incl. assist, bundle), `integration/` (controller, UI smoke, Nebius client against a fake transport), `end_to_end/` (demo), `evaluation/edit_tasks.json` (benchmark task set, in progress) |
| `docs/SPEC_TREE.txt` | the specification's tree verbatim; `bundle_project.py` uses it to mark each entry ✔ exists / ○ planned |

## Deviations from the original plan (and why)

| Planned | Actual | Reason |
|---|---|---|
| `application/commands.py` | not created | the editor's `Command` classes already are the application commands; a second layer would only forward calls |
| `domain/{project,component,layout,interaction,validation}.py` | only `typography.py`, `color_system.py` | Project/Component live in `application/` and `design_ir/`; duplicating them in `domain/` would create two representations of one thing |
| `evaluation/{functional,text,layout}_metrics`, `report` | `text_metrics`, `layout_metrics`, `geometry_metrics`, `image_metrics`, `evaluator`, `issues`, `report` | `issues.py` is the vocabulary shared with `repair/`; `evaluator.py` composes the metrics. `functional_metrics` waits for generated apps (Phase 8) |
| `layout/{hierarchy,responsive_rules}.py` | hierarchy lives in `vision/layout_inference.py` (containment) and `layout/grouping.py`; added `layout/overlap.py` | hierarchy is derived from detections; responsive rules are not needed until generation |
| `orchestration/workflow.py` only | added `repair_workflow.py`, `sketch_workflow.py` | the two concrete workflows |
| `ui/{layer_panel,training_panel,dataset_panel,settings_dialog,workspace,widgets/}` | not created | no layers/training/datasets features yet; the tree doubles as layer view |
| `vision/perspective.py` | not created | perspective correction is not started (see KNOWN_LIMITATIONS) |
| (not in the specification) `assist/` | added | natural-language edits need a home that may depend on `integrations/` (only via the provider interface) while `vision/ layout/ evaluation/ repair/ rendering/ editor/ design_ir/ domain/` stay import-free of providers; an architecture test enforces that |
| `uv.lock`, `LICENSE` | absent | lockfile not produced; licence is the owner's decision |

## Planned (not started)

`models/` (component detector, layout model), `training/`, `datasets/` (registry, manifest schema,
adapters, licence audit, dedup, splitting), `integrations/nvidia/{runtime,local_inference,compatibility}`, `generation/`
(frontend, backend), `execution/` (sandbox), `verification/`, `retrieval/`, plus the matching
`config/*.yaml`, `scripts/*` and docs from the specification. Each is created when its phase begins.
