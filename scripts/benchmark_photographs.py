#!/usr/bin/env python
"""Evaluate detections on manually annotated photographed sketches.

Manifest JSON is a list of records with ``image`` and ``truth`` paths. Truth files use
the synthetic benchmark format (a ``components`` list with type and pixel bbox). Paths
are relative to the manifest. Photographs and annotations are deliberately not bundled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sketchforge.evaluation.benchmark_runner import gt_to_items, result_to_items  # noqa: E402
from sketchforge.evaluation.component_metrics import score_detection  # noqa: E402
from sketchforge.vision.image_loader import load_image  # noqa: E402
from sketchforge.vision.pipeline import analyze  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="JSON list of image/truth path pairs")
    parser.add_argument("--out", default="experiments/results/photo_benchmark.json")
    args = parser.parse_args()
    manifest = Path(args.manifest).resolve()
    records = json.loads(manifest.read_text(encoding="utf-8"))
    results = []
    for record in records:
        image_path = manifest.parent / record["image"]
        truth_path = manifest.parent / record["truth"]
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        result = analyze(load_image(image_path))
        scores = score_detection(result_to_items(result), gt_to_items(truth))
        results.append({"image": record["image"], "scores": scores.__dict__,
                        "perspective_corrected": result.perspective.corrected,
                        "notes": result.notes})
    summary = {
        "images": len(results),
        "mean_f1": round(sum(item["scores"]["f1"] for item in results) / len(results), 4)
        if results else 0.0,
        "mean_type_accuracy": round(sum(item["scores"]["type_accuracy"] for item in results)
                                     / len(results), 4) if results else 0.0,
        "mean_iou": round(sum(item["scores"]["mean_iou"] for item in results) / len(results), 4)
        if results else 0.0,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "cases": results}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
