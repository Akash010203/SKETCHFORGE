"""Evaluate a trained component detector checkpoint against synthetic benchmarks.

Loads a saved ``.pt`` checkpoint, runs inference on held-out synthetic sketches,
and produces a detailed evaluation JSON in ``experiments/results/``.

Usage
-----
    python -I scripts/evaluate_component_detector.py \\
        --checkpoint checkpoints/component_detector_v1/best.pt

    # Compare against the deterministic CV baseline:
    python -I scripts/evaluate_component_detector.py \\
        --checkpoint checkpoints/component_detector_v1/best.pt \\
        --compare-baseline

Requirements
------------
* PyTorch must be installed.
* The checkpoint must have been created by ``train_component_detector.py``.
* Results are reported on *synthetic* sketches only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sketchforge.datasets.synthetic_generator import (  # noqa: E402
    CONDITIONS,
    HELDOUT_LAYOUTS,
    TUNING_LAYOUTS,
)
from sketchforge.evaluation.benchmark_runner import run_benchmark  # noqa: E402


def _run_cv_baseline(layouts, conditions, seeds):
    """Run the existing deterministic CV pipeline as the comparison baseline."""
    print("  Running deterministic CV baseline …")
    summary = run_benchmark(layouts, list(conditions), seeds)
    agg = summary.aggregate()["all"]
    return {
        "f1": agg.get("f1", 0),
        "precision": agg.get("precision", 0),
        "recall": agg.get("recall", 0),
        "type_accuracy": agg.get("type_accuracy", 0),
        "mean_iou": agg.get("mean_iou", 0),
    }


def _run_model_inference(checkpoint_path: Path, layouts, conditions, seeds):
    """Run the trained model on synthetic sketches and return metrics."""
    try:
        import torch
        from sketchforge.models.component_detector.architecture import ComponentDetector
        from sketchforge.models.component_detector.inference import run_inference
    except ImportError as exc:
        print(f"  ERROR: {exc}")
        return None

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(str(checkpoint_path), map_location=device, weights_only=True)

    num_classes = ckpt.get("num_classes", 15)
    model = ComponentDetector(num_classes=num_classes).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"  Loaded checkpoint: epoch {ckpt.get('epoch', '?')} | val metric {ckpt.get('val_metric', '?')}")

    from sketchforge.datasets.synthetic_generator import ALL_LAYOUTS, render_sketch
    from sketchforge.evaluation.component_metrics import BoxItem, score_detection

    true_pos = false_pos = false_neg = 0
    iou_sum = 0.0
    n_cases = 0

    for layout_name, layout_fn in layouts.items():
        for cond_name in conditions:
            for seed in seeds:
                spec = layout_fn()
                image, truth = render_sketch(spec, seed=seed, condition=cond_name)
                preds = run_inference(model, image, device=device)

                gt_items = [
                    BoxItem(c["type"], tuple(c["bbox"]))
                    for c in truth["components"] if c["type"] != "page"
                ]
                pred_items = [BoxItem(p["type"], tuple(p["bbox"])) for p in preds]
                scores = score_detection(pred_items, gt_items)
                true_pos += scores.true_pos
                false_pos += scores.false_pos
                false_neg += scores.false_neg
                iou_sum += scores.mean_iou
                n_cases += 1

    if n_cases == 0:
        return None

    precision = true_pos / max(true_pos + false_pos, 1)
    recall = true_pos / max(true_pos + false_neg, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "type_accuracy": None,  # not available from inference directly
        "mean_iou": round(iou_sum / n_cases, 4),
        "cases": n_cases,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--checkpoint", required=True,
                    help="Path to the .pt checkpoint file")
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13],
                    help="Random seeds for synthetic sketches (default: 11 12 13)")
    ap.add_argument("--compare-baseline", action="store_true",
                    help="Also run the deterministic CV baseline for comparison")
    ap.add_argument("--out", default="experiments/results/model_evaluation.json",
                    help="Output path for the evaluation report")
    args = ap.parse_args()

    checkpoint = ROOT / args.checkpoint
    if not checkpoint.is_file():
        print(f"ERROR: checkpoint not found: {checkpoint}")
        print("  Train a model first: python -I scripts/train_component_detector.py")
        return 1

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SketchForge Component Detector — Held-Out Evaluation")
    print("=" * 60)
    print(f"  Checkpoint: {checkpoint}")
    print(f"  Seeds:      {args.seeds}")
    print()

    report = {
        "checkpoint": str(checkpoint),
        "seeds": args.seeds,
        "synthetic_only": True,
        "note": "All numbers are from synthetic sketches. Do not report as real-sketch results.",
        "groups": {},
    }

    for label, layouts in (
        ("tuning_layouts", TUNING_LAYOUTS),
        ("heldout_layouts", HELDOUT_LAYOUTS),
    ):
        print(f"Group: {label}")
        cond_names = list(CONDITIONS.keys())

        t0 = time.perf_counter()
        model_metrics = _run_model_inference(checkpoint, layouts, cond_names, args.seeds)
        elapsed = time.perf_counter() - t0

        group_result: dict = {
            "layouts": sorted(layouts.keys()),
            "model": model_metrics or "evaluation_failed",
            "elapsed_seconds": round(elapsed, 1),
        }

        if model_metrics:
            print(f"  Model:    F1={model_metrics['f1']:.3f}  "
                  f"P={model_metrics['precision']:.3f}  R={model_metrics['recall']:.3f}  "
                  f"IoU={model_metrics['mean_iou']:.3f}")
        else:
            print("  Model:    evaluation failed (check PyTorch installation)")

        if args.compare_baseline:
            t0 = time.perf_counter()
            cv_metrics = _run_cv_baseline(layouts, cond_names, args.seeds)
            cv_elapsed = time.perf_counter() - t0
            group_result["cv_baseline"] = cv_metrics
            group_result["baseline_elapsed_seconds"] = round(cv_elapsed, 1)

            print(f"  Baseline: F1={cv_metrics['f1']:.3f}  "
                  f"P={cv_metrics['precision']:.3f}  R={cv_metrics['recall']:.3f}  "
                  f"IoU={cv_metrics['mean_iou']:.3f}")

            if model_metrics:
                delta = model_metrics["f1"] - cv_metrics["f1"]
                direction = "↑ IMPROVEMENT" if delta > 0 else ("↓ REGRESSION" if delta < -0.005 else "≈ NEUTRAL")
                print(f"  ΔF1: {delta:+.3f}  {direction}")
        print()

        report["groups"][label] = group_result

    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Evaluation report saved to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
