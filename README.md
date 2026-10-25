# SketchForge

SketchForge is a local-first workbench for turning a photo of a hand-drawn interface into an
editable design. It detects the layout, builds a structured Design IR, renders it, checks it for
layout problems, and keeps only repairs that improve the measured result without causing a
regression.

The browser Studio is the main interface. Its API and the desktop compatibility workbench share
the same Python services, so importing, editing, rendering, measuring, and repairing follow the
same path.

The core sketch-to-design loop and the generation pipeline are implemented. The repository also
contains Nebius integration, natural-language edit planning, React/TypeScript and Python backend
generation, and sandboxed verification. The checked-in test record is 318 tests with no skips;
run the commands below to verify the state of your checkout. Feature-level evidence and known
limits live in [TASKS.md](TASKS.md) and [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## Product direction

The project is organised around two practical phases.

Phase 1 turns a sketch, screenshot, or photographed drawing into an editable design. OpenCV
preprocessing, component detection, OCR when enabled, geometric relationships, typography, colour,
spacing, and alignment feed the Design IR. The IR gives the editor concrete components to change:
for example, a user can change a button colour, move a card, or replace text without editing raw
pixels.

Phase 2 turns that structured design into a working project. It generates a frontend and optional
Python backend, captures the rendered result, compares it with the intended layout, and uses the
existing repair loop to make and verify bounded corrections. Remote generation is optional and
goes through Nebius; the local deterministic fallback remains available when no credential is set.

Training and retrieval are deliberately separate from the editor path. Dataset adapters and local
hybrid retrieval exist, but large training data, trained weights, and claims about real-world
photograph accuracy must be supported by measured results before they become product promises.

## Try it in two minutes

Requirements: Python 3.11+ (developed on 3.13). PySide6 is optional and only needed for the
legacy desktop compatibility workbench.

```bash
uv venv --python 3.13 .venv                    # or: python -m venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"

.venv/bin/python -m sketchforge demo           # headless end-to-end demo, ~1.5 s, no credentials
.venv/bin/python -m sketchforge studio         # primary browser UI: http://127.0.0.1:8000/studio
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

### In the browser Studio

1. Start `python -m sketchforge studio` and open `http://127.0.0.1:8000/studio`.
2. Drag in a PNG/JPEG/WebP sketch. Studio validates it, analyzes it, and retains the canonical
   Design IR for the next generation.
3. Describe the application. Generation runs through the Hybrid Orchestrator; the job log shows
   analysis, file generation, preview, and verification states. The result is labelled
   `ai_generated`, `mixed`, or `template_fallback`.
4. Inspect the generated preview, export the project ZIP, and submit supported natural-language
   revisions from the prompt. A skipped or failed verification is shown as such; it is not a pass.

### Desktop compatibility workbench

1. *File → Open sample sketch* (or *Import sketch…*). Import runs on a background thread.
2. Click or drag on the canvas, or pick a row in **Components**; edit text, fill, border, text
   colour, X/Y/width/height, font size, corner radius in **Properties** (every edit is undoable).
3. **Measure & repair → Inject fault → Auto-repair**. The repair runs on a copy of the design,
   is verified, and is applied as **one** undo step. The report appears below the issue table.
4. *File → Save project* writes a folder (`project.json`, `design.json`, the source sketch,
   renders, reports); *Export design…* writes SVG/HTML/CSS/PNG/JSON.

## How it works

```
Browser Studio ─▶ Web API ─▶ Hybrid Orchestrator ─▶ vision │ Design IR │ generation │ preview │ verification
                    │
Desktop compatibility ─▶ AppController ─▶ shared workflows │ editor │ rendering
```

`sketch image → preprocess (illumination flattening, threshold variants) → shapes / lines / text
blobs → rule-based classification with ambiguity flags → containment hierarchy → alignment and
spacing snapping → Design IR → SVG / HTML / CSS / PNG → evaluator → repair engine`.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DESIGN_IR_SPEC.md](docs/DESIGN_IR_SPEC.md),
[docs/EVALUATION.md](docs/EVALUATION.md).

## Measured results

Synthetic measurements are useful regression signals, not real-sketch performance. The checked-in
real-photo result in `experiments/results/current_real_photo.json` is poor: one photographed
grid-paper sketch scored F1 **0.0333** and type accuracy **0.0000**. Do not treat sketch detection
as production-ready for photographs.

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

### Offline handwriting OCR

Handwriting recognition is opt-in. Install the training dependencies and train a local CRNN-CTC
checkpoint on the downloaded Teklia/IAM-line dataset:

```powershell
pip install -e .[ocr-train]
python scripts/train_handwriting_ocr.py --epochs 12
$env:SKETCHFORGE_OCR_MODEL = "checkpoints/handwriting_ocr.pt"
```

The checkpoint runs on CPU and does not access the network. The alternative Hugging Face TrOCR
path remains available by setting `SKETCHFORGE_OCR_MODEL` to a local model directory or model ID.
Training data is not bundled; see `scripts/download_datasets.py --dataset teklia-iam-line`.
| Repair matrix: 337 injected faults (7 kinds × 5 layouts × 5 conditions × 2 seeds) | fault detected 98.8 %, fully repaired 97.0 %, no issues left 95.0 %, **regressed 0 %**, median repair 308 ms |

Reproduce: `python scripts/evaluate_layout.py`, `python scripts/evaluate_repair.py` (results in
`experiments/results/`). Failure analysis: [docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md).

## Tests

```bash
pytest tests -q                       # 318 tests, ~35 s; 0 failed, 0 skipped
ruff check src tests scripts
```

## Optional Nebius / Nemotron generation

Without credentials, Studio uses the deterministic template fallback and labels it clearly. To
enable the remote generator, copy `.env.example` to an ignored `.env` (or set an environment
variable) and set `NEBIUS_API_KEY`; then run `python scripts/verify_nebius.py --enable --accept-egress`
to perform an explicit live probe. A mocked test is not evidence of a live model call. See
[docs/NEBIUS_NVIDIA_INTEGRATION.md](docs/NEBIUS_NVIDIA_INTEGRATION.md) for model and privacy details.

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

Released under the MIT License. See LICENSE for details.
