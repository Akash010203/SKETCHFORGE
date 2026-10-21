#!/usr/bin/env python
"""Run the three-arm natural-language edit benchmark.

Usage: python scripts/run_visual_benchmark.py [--arms local model hybrid]
       [--tasks tests/evaluation/edit_tasks.json] [--out experiments/results/edit_benchmark.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sketchforge.assist.edit_benchmark import load_tasks, run_benchmark  # noqa: E402
from sketchforge.integrations.nebius import ConsentGate, NebiusClient, egress_notice, load_nebius_config  # noqa: E402
from sketchforge.integrations.provider_interface import ProviderAuthError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", default="tests/evaluation/edit_tasks.json")
    parser.add_argument("--arms", nargs="+", choices=("oracle", "local", "model", "hybrid"),
                        default=("local", "model", "hybrid"),
                        help="local baseline, model-only, and integrated hybrid; oracle is an optional reference control")
    parser.add_argument("--accept-egress", action="store_true",
                        help="acknowledge the Nebius egress notice before running the model arm")
    parser.add_argument("--enable", action="store_true",
                        help="enable the provider for this run without editing config/providers.yaml")
    parser.add_argument("--out", default="experiments/results/edit_benchmark.json")
    args = parser.parse_args()
    provider = None
    if "model" in args.arms or "hybrid" in args.arms:
        overrides = {"enabled": True} if args.enable else {}
        config = load_nebius_config(overrides=overrides)
        if config.enabled:
            print(egress_notice(config))
            if not args.accept_egress:
                parser.error("model/hybrid arms need --accept-egress after reviewing the notice")
            try:
                config.api_key()
            except ProviderAuthError as exc:
                parser.error(str(exc))
            consent = ConsentGate()
            consent.acknowledge()
            provider = NebiusClient(config, consent)
        elif "model" in args.arms:
            parser.error("the model arm requires nebius.enabled: true in config/providers.yaml or --enable")
    result = run_benchmark(load_tasks(args.tasks), arms=tuple(args.arms), provider=provider)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print(f"wrote {out}")
    # A benchmark run succeeds when every requested task was evaluated; arm scores are data.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
