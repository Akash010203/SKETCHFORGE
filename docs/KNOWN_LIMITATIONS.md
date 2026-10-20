# Known limitations

Read these before relying on any result. Each entry is something that was observed or is true by
construction, not a hypothetical.

## Evidence

* **No real sketches have been tested.** Every detection and repair number comes from sketches
  produced by our own generator (wobbly strokes, shadows, noise, blur, JPEG). Real handwriting,
  paper curl, pen variety, glare and phone-camera perspective are untested; expect lower numbers.
* The classifier rules were tuned on three layouts; two other layouts were held out and scored
  slightly differently (type accuracy 0.985 vs 0.946). The held-out set is small (42 sketches).
* Confidence values (`type_scores`) are rule scores, **not calibrated probabilities**.

## Vision

* Perspective correction now attempts to detect and rectify one dominant page quadrilateral.
  This is heuristic and may fail on cluttered scenes, curled pages, weak borders or shadows;
  the photo benchmark remains unrun because no photographed samples/annotations are checked in.
* **Handwriting OCR is optional.** Install `sketchforge[ocr]` and set `SKETCHFORGE_OCR_MODEL` to
  `microsoft/trocr-base-handwritten` (or a local compatible TrOCR model) to recognize candidate
  text lines. The first run may download model weights. Recognition is best-effort: missed or
  unreadable text remains a clearly flagged placeholder (`text_is_inferred = true`); verify OCR
  output before relying on it. OCR is off by default.
* A sketch needs a visible page frame or consistent margins to find the page area; with no drawn
  frame the ink bounding box is used and noted.
* Known confusions: card ↔ container, checkbox ↔ radio when poorly drawn, text ↔ heading (heading
  is decided by relative height), text-line splitting under very thin, very thick or blurred
  strokes (`thin` condition is the weakest: held-out F1 0.915).
* A large squarish ink cluster is classified as image with `heading` close behind (flagged ambiguous).
* Blank or near-blank images raise a clear error rather than returning an empty design.

## Layout, evaluation and repair

* Text fit uses an **estimated** glyph width (± ~10 %), not a font engine.
* Repair rules cover the 10 issue codes through geometric edits only (translate, resize, restyle,
  reduce font size to a floor of 10 px). They cannot fix problems that need new content or a
  redesign; those are reported as remaining.
* Repair success is partly "trial and reject": some candidates (widen, shrink) are tried and rolled
  back by the regression check. This is by design and recorded in the report.
* On drawings whose *baseline* (before any injected fault) already contains detection artefacts
  (e.g. the `settings_page` sketch under `thin` strokes produces several overlapping text boxes),
  the engine can stall: it stops after the no-progress window instead of redesigning. See
  EXPERIMENT_LOG for the matrix failures.
* Injected faults are our own; the matrix measures how well the engine repairs *those*, not
  arbitrary user mistakes.

## Application

* Desktop UI verified on Qt's **offscreen** platform only; no interactive display was available in the
  build environment, so real-window look-and-feel, high-DPI behaviour and platform file dialogs were
  not exercised.
* The canvas supports select, drag-move and a bottom-right resize handle; there is no
  add/delete-component tool, multi-select drag or snapping yet.
* Project files store the design, source sketch, renders and reports, but **not** vision
  detections (re-import regenerates them) or the undo history.
* Only one document is open at a time.

## Currently in progress / remaining items

* **Vision**: Collect and annotate licensed photographed sketches, then run `scripts/benchmark_photographs.py`. The benchmark runner is implemented, but no photograph scores are available until a non-empty local manifest and its image/annotation files are supplied.
* **Models & Training**: Architecture and training loop for the compact component detector are implemented (`models/component_detector/`, `training/trainer.py`); actual training run and checkpoint generation (`checkpoints/component_detector.pt`) are pending. `models/layout_model/` is planned.
* **Integrations**: Nebius client is implemented and verified against an in-process mock transport; live verification requires running `scripts/verify_nebius.py` with a valid `NEBIUS_API_KEY`. NVIDIA local runtime hooks (`integrations/nvidia/runtime.py`) are pending.
* **Testing & Execution**: Sandboxed execution and verification runners are implemented, with dedicated unit tests in progress. Full browser automation (Playwright/Chrome) requires host browser configuration.
* **Application**: Desktop UI primary workflow is operational; secondary panels (`layer_panel.py`, `settings_dialog.py`, `training_panel.py`, `dataset_panel.py`) and the natural-language "Ask" prompt bar are pending integration.

## Hardware & Environment

Verified local workstation environment:
* **OS**: Windows 11 (AMD64)
* **CPU**: 12 logical cores
* **GPU**: NVIDIA GeForce RTX 4050 Laptop GPU (6,141 MiB VRAM, Driver 591.74)
* **PyTorch**: 2.6.0+cu124 with CUDA 12.4 acceleration enabled
* **Storage**: 728.19 GB total, 443.90 GB free (planning budget: 221.95 GB)
* **Training capability**: Full CUDA GPU acceleration is available locally for training compact detectors and layout models.
