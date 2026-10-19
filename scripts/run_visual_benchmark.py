#!/usr/bin/env python
"""Run the deterministic natural-language edit benchmark.

Usage: python scripts/run_visual_benchmark.py [--arms oracle local hybrid]
       [--tasks tests/evaluation/edit_tasks.json] [--out experiments/results/edit_benchmark.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sketchforge.assist.edit_benchmark import load_tasks, run_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", default="tests/evaluation/edit_tasks.json")
    parser.add_argument("--arms", nargs="+", choices=("oracle", "local", "hybrid"),
                        default=("oracle", "local", "hybrid"))
    parser.add_argument("--out", default="experiments/results/edit_benchmark.json")
    args = parser.parse_args()
    result = run_benchmark(load_tasks(args.tasks), arms=tuple(args.arms))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print(f"wrote {out}")
    # A benchmark run succeeds when every requested task was evaluated; arm scores are data.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
