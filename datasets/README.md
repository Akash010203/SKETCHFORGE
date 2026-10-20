# Datasets

The manifest and audit workflow are in `manifests/`. External data is not downloaded automatically. Review the license and access notes before placing data in `raw/`; generated and processed data stays out of version control. The current local sample sketches live in `assets/sample_sketches/`.

## Photographed sketch evaluation

One CC0 smartphone photograph of a paper UI sketch and manual annotation are checked in under `evaluation/`; its provenance, scope, and benchmark command are documented in `evaluation/README.md`. This one-image fixture enables regression measurement in CI, but is too small to support broad real-world accuracy claims. Additional photographs and manually annotated truth JSON can be added with their licensing/access notes. Truth boxes use original image pixel coordinates. Include the page as a `page` component when evaluating frame localization.

Create a manifest JSON list with relative paths, for example `[{"image":"raw/photo-01.jpg","truth":"annotations/photo-01.json"}]`, then run `python scripts/benchmark_photographs.py datasets/my_photos/manifest.json`. The output reports per-image scores and aggregate F1, type accuracy, and IoU. Keep external data licensing and attribution with each fixture.
