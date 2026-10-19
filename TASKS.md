# Task ledger

Statuses: `NOT_STARTED` · `IN_PROGRESS` · `IMPLEMENTED` (code exists) · `TESTED` (an automated test
ran and passed) · `VERIFIED` (acceptance criterion measured and recorded) · `BLOCKED`.
A feature is not VERIFIED because it compiles. Last updated with the 269-test run on 2026-10-19.

## Milestone 1 — sketch → editable design → measured, verified repair

| # | Feature | Status | Evidence / acceptance |
|---|---|---|---|
| 1 | Design IR schema, validation, serialization, versioning/migrations | VERIFIED | `tests/unit/test_design_ir.py`; round-trip hash equality; unknown fields rejected |
| 2 | Safe image loading (type, size, magic bytes, pixel budget) | TESTED | `tests/unit/test_vision.py` (bad/oversized/tiny/corrupt inputs) |
| 3 | Preprocessing (illumination flattening, threshold variants, stroke width) | TESTED | shadow/noise/blur conditions in detection benchmark; flatten test |
| 4 | Shape / line / text-region detection and rule-based classification with ambiguity | VERIFIED (synthetic only) | held-out F1 0.982, type acc 0.946 (`experiments/results/detection_benchmark.json`) |
| 5 | Hierarchy, alignment, spacing and repeated-group inference → Design IR | TESTED | `tests/unit/test_layout.py`, `test_sketch_to_ir.py` |
| 6 | Perspective correction (`vision/perspective.py`) | NOT_STARTED | planned; see KNOWN_LIMITATIONS |
| 7 | Renderers: SVG, nested HTML, CSS, PNG snapshot (deterministic) | TESTED | `tests/unit/test_renderer.py` |
| 8 | Editor: undoable commands, locks, selection, property editing | TESTED | `tests/unit/test_editor.py`; exact undo to the original hash |
| 9 | Evaluator: 10 issue codes + fidelity vs sketch + SSIM/pixel metrics | TESTED | `tests/unit/test_metrics.py` |
| 10 | Repair engine: diagnose → candidates → trial → regression check → accept / exact rollback | VERIFIED (synthetic) | 337-cell matrix: 97.0 % repaired, 0 % regressed |
| 11 | Orchestration: step registry, budgets, stopping rules, history, cancel | TESTED | `tests/unit/test_repair.py` (limits, no-progress, 3-attempt cap) |
| 12 | Application controller (Qt-free), events, background tasks, project store | TESTED | `tests/integration/test_controller.py` |
| 13 | Desktop UI (tree, canvas with drag/resize, properties, measure & repair, code) | TESTED | `tests/integration/test_ui_smoke.py` (offscreen Qt, 8 tests) |
| 14 | CLI `demo` / `gui` / `info`, sample sketches, reproducible demo | VERIFIED | `tests/end_to_end/test_first_demo.py`; README steps run |
| 15 | Before/after report (JSON, Markdown, PNG comparison) | VERIFIED | demo output inspected |

**Milestone 1 exit criteria**: launches ✔ (offscreen-verified; no interactive display available in the
build environment) · import ✔ · preprocessing + detection ✔ · valid IR ✔ · renderer ✔ · editable ✔ ·
evaluator measures a known issue ✔ · repair fixes predefined issues ✔ · before/after recorded ✔ ·
automated tests ✔ · README reproduces the demo ✔.
Caveat: the sample sketches are **synthetic**; no real photographed sketch has been tested.

## Later phases

| Phase | Item | Status | Notes |
|---|---|---|---|
| 4 | Verify official NVIDIA/Nebius hackathon rules | VERIFIED | recorded in `docs/NEBIUS_NVIDIA_INTEGRATION.md` §1 (deadline Fri 30 Oct 2026 10:00 PT; Apache-2.0/MIT/MPL-2.0 licence required; hosting our own server is excluded) |
| 4 | Provider interface + isolated `integrations/nebius/` client, consent gate, privacy limits | TESTED | 32 tests against an in-process fake transport. **A live call to the real service has never been made** (no key; the sandbox proxy blocks the host) |
| 4 | Live verification (`scripts/verify_nebius.py`) | NOT_STARTED | must be run by the owner with `NEBIUS_API_KEY` on a networked machine |
| 4 | Model-vs-local benchmark (3 arms) | IN_PROGRESS | task set `tests/evaluation/edit_tasks.json` drafted (58 tasks); scoring harness, oracle validation and arms not written yet. **No model result exists** |
| 5 | Dataset audit, manifest schema, pilot subset | NOT_STARTED | free disk ~29 GB (budget ~14.7 GB); no downloads yet |
| 5 | Synthetic data generator (original) | IMPLEMENTED | `datasets/synthetic_generator.py`: strokes, shadows, noise, exact truth; no UI-render pairs yet |
| 6 | Train compact detector from random init | NOT_STARTED | no GPU, 2 CPUs, 7.8 GB RAM, PyTorch not installed |
| 7 | Natural-language edits: plan schema, summary, local parser, model planner, verified apply | TESTED | `tests/unit/test_assist.py` (58 tests; stub provider; mutation-checked). UI "Ask" bar not written |
| 8 | Frontend generation (React/TS) + verification | NOT_STARTED | Node 22 available |
| 9 | Backend generation | NOT_STARTED | |
| 10 | Restricted execution + full-app verification | NOT_STARTED | |
| 11 | Performance + packaging | NOT_STARTED | `scripts/bundle_project.py` (one-file bundle, 5 round-trip tests) is a first piece |

## Needs the owner

* Choose a `LICENSE` (the hackathon requires Apache-2.0, MIT or MPL-2.0 visible at the repository top).
* Provide `NEBIUS_API_KEY` and run the live check and benchmark on a machine that can reach Nebius.
* Register and submit on Devpost before the deadline above; read the full Official Rules.

## Next single action

Finish the edit benchmark: write the scoring harness (`assist/edit_benchmark.py`) and validate the
58 tasks with an *oracle* arm (the reference plan must pass its own expectations) before running any
planner against them; then `scripts/run_visual_benchmark.py` (local arms run here; model arms need
a key, and can be replayed offline from a recorded run).
