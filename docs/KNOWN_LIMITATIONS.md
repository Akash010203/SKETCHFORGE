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

* **No perspective / skew correction** (`vision/perspective.py` not implemented). A photographed
  sketch taken at an angle will mis-measure.
* **No OCR / handwriting recognition.** Sketch text is scribble; text content is *unknown* and is
  replaced by clearly flagged placeholder strings (`text_is_inferred = true`), e.g. "Lorem ipsum".
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

## Not built yet

NVIDIA/Nebius integration, dataset pipeline, trained models, natural-language edits, React/TS and
Python backend generation, sandboxed execution and verification, packaging. See TASKS.md.

## Hardware

Development machine: 2 CPU cores, 7.8 GB RAM, **no GPU**, PyTorch not installed, ~29 GB free disk.
Training in Phase 6 is therefore limited to very small CPU models.
