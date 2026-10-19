#!/usr/bin/env python
"""Explicitly verify Nebius Token Factory access and NVIDIA model availability.

No sketch or design data is sent. The only completion is a fixed one-word connectivity probe.
The endpoint does not expose an account's retention setting, so ZDR is reported as unknown.

Usage: set NEBIUS_API_KEY, enable the provider in config/providers.yaml, then run:
       python scripts/verify_nebius.py --accept-egress
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sketchforge.integrations.nebius import (  # noqa: E402
    ConsentGate,
    NebiusClient,
    egress_notice,
    load_nebius_config,
)
from sketchforge.integrations.nebius.model_registry import nvidia_models, parse_models  # noqa: E402
from sketchforge.integrations.provider_interface import (  # noqa: E402
    ChatMessage,
    CompletionRequest,
    ProviderError,
)

PREFERRED = ("nvidia/Nemotron-3_5-Lightning", "nvidia/nemotron-3-super-120b-a12b")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accept-egress", action="store_true",
                        help="acknowledge the displayed Nebius egress notice for this invocation")
    parser.add_argument("--model", help="override the configured model for the completion probe")
    args = parser.parse_args()
    config = load_nebius_config()
    print(egress_notice(config))
    if not args.accept_egress:
        print("\nNo request sent. Review the notice, then rerun with --accept-egress to proceed.", file=sys.stderr)
        return 2
    if not config.enabled:
        print("\nNo request sent: set nebius.enabled: true in config/providers.yaml.", file=sys.stderr)
        return 2

    consent = ConsentGate()
    consent.acknowledge()
    client = NebiusClient(config, consent)
    report: dict = {
        "provider": "nebius",
        "endpoint": config.base_url,
        "zdr": {"status": "unknown", "reason": "The inference API does not expose the organization retention setting."},
        "privacy_policy": {
            "allow_images": config.privacy.allow_images,
            "include_user_text": config.privacy.include_user_text,
            "probe_contains_design_data": False,
        },
    }
    try:
        raw = client.list_models()
        models = parse_models(raw)
        ids = {model.model_id for model in models}
        available = [model_id for model_id in PREFERRED if model_id in ids]
        chosen = args.model or (available[0] if available else config.default_model)
        report["models_endpoint"] = {"ok": True, "count": len(models),
                                     "nvidia_models": [m.model_id for m in nvidia_models(models)],
                                     "preferred_available": available}
        result = client.complete(CompletionRequest(
            messages=(ChatMessage("user", "Reply with the single word: ok"),),
            purpose="verify_nebius", max_tokens=8, model=chosen,
        ))
        report["completion"] = {"ok": bool(result.text.strip()), "model": result.model,
                                 "latency_ms": round(result.latency_ms, 1),
                                 "prompt_tokens": result.usage.prompt_tokens,
                                 "completion_tokens": result.usage.completion_tokens}
        report["model_verified"] = chosen in available
        report["ok"] = report["completion"]["ok"] and chosen in available
    except ProviderError as exc:
        report["ok"] = False
        report["error"] = str(exc)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
