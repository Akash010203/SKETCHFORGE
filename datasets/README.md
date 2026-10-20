# Datasets

The manifest and audit workflow are in `manifests/`. External data is not downloaded automatically. Review the license and access notes before placing data in `raw/`; generated and processed data stays out of version control. The current local sample sketches live in `assets/sample_sketches/`.

## Photographed sketch evaluation

No photographed sketches or photo annotations are currently available in this repository, so photo benchmark scores cannot yet be reported. Add photographs and manually annotated truth JSON under a local dataset directory, keeping licensing/access details with the data. The truth format matches the synthetic generator: a JSON object with a `components` array of `{ "type": ..., "bbox": [x, y, width, height] }` entries in original image pixels. Include the page as a `page` component when evaluating frame localization.

Create a manifest JSON list with relative paths, for example `[{"image":"raw/photo-01.jpg","truth":"annotations/photo-01.json"}]`, then run `python scripts/benchmark_photographs.py datasets/my_photos/manifest.json`. The output reports per-image scores and aggregate F1, type accuracy, and IoU. Store real data locally; it is not committed by this workflow.
