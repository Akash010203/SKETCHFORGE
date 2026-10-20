# SketchForge

A local-first desktop workbench that turns a photo of a hand-drawn UI sketch into a structured,
**editable** design, then **measures** that design, finds layout faults, proposes the smallest
patch that fixes each one, re-renders, re-measures, and **keeps the patch only if the numbers
improve and nothing else gets worse**.

The closed loop (create → measure → diagnose → patch → verify → accept or roll back) is the point
of the project. Everything runs in one Python process on your machine: **no web server, no REST
API, no network requests** in the application itself.

> **Status: Core workbench & generation pipeline operational** (sketch → Design IR → editable render → measure → repair → full app generation). Milestone 1 is verified; Nebius provider integration, natural-language edit assist, React/TS and Python backend generators, and sandboxed verification are implemented. 318 automated tests pass with 0 skips. See [TASKS.md](TASKS.md) for the per-feature status and [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## Try it in two minutes

Requirements: Python 3.11+ (developed on 3.13). The GUI additionally needs PySide6.

```bash
uv venv --python 3.13 .venv                    # or: python -m venv .venv
uv pip install --python .venv/bin/python -e ".[ui,dev]"

.venv/bin/python -m sketchforge demo           # headless end-to-end demo, ~1.5 s, no credentials
.venv/bin/python -m sketchforge gui            # desktop workbench (needs a display)
```

The demo imports `assets/sample_sketches/login_page_synthetic.png`, detects components, builds and
validates a Design IR, renders it, **injects a known fault** (an input pushed 30 px out of its
card), has the evaluator find it, lets the repair engine fix it, and writes everything to
`output/demo/`:

| Look at | What it shows |
|---|---|
| `output/demo/reports/repair_report.md` | before/after metrics, every attempt with its decision and reason |
| `output/demo/reports/repair_report_comparison.png` | red = faulty design, green = repaired design |
| `output/demo/renders/{before,after}_repair.{svg,html,css,png}` | the editable design in every export format |
| `output/demo/design_{initial,before_repair,final}.json` | the Design IR at each stage |
| `output/demo/diagnostics/detections.png` | what the vision stage thought it saw |
| `output/demo/summary.json` | step timings, hashes, and `"network": "none"` |

Other faults: `--inject {overflow,misalignment,spacing,text_overflow,low_contrast,small_control,overlap,none}`;
your own drawing: `--image path/to/photo.jpg`; measure only: `--no-repair`.
Headless screenshot of the GUI: `python -m sketchforge gui --screenshot window.png`.

### In the desktop app

1. *File → Open sample sketch* (or *Import sketch…*). Import runs on a background thread.
2. Click or drag on the canvas, or pick a row in **Components**; edit text, fill, border, text
   colour, X/Y/width/height, font size, corner radius in **Properties** (every edit is undoable).
3. **Measure & repair → Inject fault → Auto-repair**. The repair runs on a copy of the design,
   is verified, and is applied as **one** undo step. The report appears below the issue table.
4. *File → Save project* writes a folder (`project.json`, `design.json`, the source sketch,
   renders, reports); *Export design…* writes SVG/HTML/CSS/PNG/JSON.

## How it works

```
Desktop UI ─▶ AppController ─▶ workflows ─▶ vision │ layout │ evaluation │ repair │ rendering │ editor
 (PySide6)     (no Qt types)    (in-process calls, background tasks, events)
```

`sketch image → preprocess (illumination flattening, threshold variants) → shapes / lines / text
blobs → rule-based classification with ambiguity flags → containment hierarchy → alignment and
spacing snapping → Design IR → SVG / HTML / CSS / PNG → evaluator → repair engine`.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DESIGN_IR_SPEC.md](docs/DESIGN_IR_SPEC.md),
[docs/EVALUATION.md](docs/EVALUATION.md).

## Measured results (synthetic sketches only)

All numbers come from sketches drawn by our own generator, whose ground truth is exact. They do
**not** describe real photographs of human drawings, which have not been tested.

### Handwriting OCR

Handwriting recognition is optional and off by default. Install the OCR extra and select the
TrOCR handwritten model before launching SketchForge:

```powershell
pip install -e ".[ocr]"
$env:SKETCHFORGE_OCR_MODEL = "microsoft/trocr-base-handwritten"
```

The first run downloads model files unless `SKETCHFORGE_OCR_MODEL` points to a compatible local
model directory. Recognized text is saved as non-inferred text; unreadable regions keep the inferred
placeholder. Review OCR output because handwriting recognition can make mistakes.

| Benchmark | Result |
|---|---|
| Component detection, tuning layouts (63 sketches, 7 photo conditions) | F1 0.973, type accuracy 0.985, mean IoU 0.840 |
| Component detection, **held-out** layouts (42 sketches) | F1 0.982, type accuracy 0.946, mean IoU 0.835 |
| Repair matrix: 337 injected faults (7 kinds × 5 layouts × 5 conditions × 2 seeds) | fault detected 98.8 %, fully repaired 97.0 %, no issues left 95.0 %, **regressed 0 %**, median repair 308 ms |

Reproduce: `python scripts/evaluate_layout.py`, `python scripts/evaluate_repair.py` (results in
`experiments/results/`). Failure analysis: [docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md).

## Tests

```bash
pytest tests -q                       # 318 tests, ~35 s; 0 failed, 0 skipped
ruff check src tests scripts
```

## Project layout

See [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md) for what exists, what is planned, and where the
implementation deliberately differs from the original plan.

## Privacy and security

The application makes **no network requests** (the demo's `summary.json` records that). Images are
validated before decoding (type, size, magic bytes, pixel budget). Nothing in the project
executes generated code yet; when code generation arrives it will run in a restricted
environment. No credentials are stored in the repository (`.env` is git-ignored). See
[docs/SECURITY.md](docs/SECURITY.md).

## License

No license has been chosen yet; that is the owner's decision. Until one is added, all rights are
reserved by default.
