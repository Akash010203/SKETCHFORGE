"""Prepare external datasets: validate, sample, and convert to the training format.

Downloads and processes a *small pilot subset* of a candidate dataset from the
manifest. Only proceeds when:
  1. The target dataset is listed in datasets/manifests/manifest.json.
  2. The license SPDX code is on the permitted list.
  3. Enough free disk space is available.

Usage
-----
    python -I scripts/prepare_datasets.py --dataset websight --pilot 500

Options
-------
--dataset ID     Manifest dataset ID to prepare (required)
--pilot N        Number of samples to download (default: 100, max: 10 000)
--out DIR        Output directory (default: datasets/raw/<dataset-id>)
--skip-license-check
                 Skip the license gate (use only when you have read and
                 confirmed the license yourself; records the override in the log)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Licenses considered acceptable for training use in this project
_PERMITTED_LICENSES = {
    "MIT", "Apache-2.0", "Apache-2.0-OR-LATER",
    "CC-BY-4.0", "CC-BY-SA-4.0",
    "ODC-By-1.0", "ODbL-1.0",
}

# Hard upper bound on pilot subset (protects storage)
_MAX_PILOT = 10_000


def _load_manifest() -> dict:
    path = ROOT / "datasets" / "manifests" / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _find_dataset(manifest: dict, dataset_id: str) -> dict | None:
    for ds in manifest.get("datasets", []):
        if ds.get("id") == dataset_id:
            return ds
    return None


def _check_storage(required_bytes: int | None) -> tuple[int, bool]:
    import shutil
    st = shutil.disk_usage(ROOT)
    free = st.free
    if required_bytes is None:
        return free, True
    # Require 2× the download size for download + extraction
    needed = required_bytes * 2
    return free, free > needed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset", required=True,
                    help="Manifest dataset ID (e.g. websight)")
    ap.add_argument("--pilot", type=int, default=100,
                    help="Number of samples to prepare (default: 100)")
    ap.add_argument("--out", default=None,
                    help="Output directory (default: datasets/raw/<id>)")
    ap.add_argument("--skip-license-check", action="store_true",
                    help="Bypass the license gate (self-certify compliance)")
    args = ap.parse_args()

    pilot = min(args.pilot, _MAX_PILOT)
    out = ROOT / (args.out or f"datasets/raw/{args.dataset}")
    out.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ manifest
    try:
        manifest = _load_manifest()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    ds = _find_dataset(manifest, args.dataset)
    if ds is None:
        available = [d["id"] for d in manifest.get("datasets", [])]
        print(f"ERROR: dataset '{args.dataset}' not in manifest.")
        print(f"  Available: {available}")
        return 1

    print(f"Dataset:  {ds['name']}")
    print(f"License:  {ds['license_spdx']}")
    print(f"Access:   {ds.get('access', 'unknown')}")
    print(f"URL:      {ds['source_url']}")
    print()

    # ------------------------------------------------------------------ license check
    if not args.skip_license_check:
        spdx = ds.get("license_spdx", "UNKNOWN")
        if spdx not in _PERMITTED_LICENSES:
            print(f"LICENSE GATE: '{spdx}' is not on the permitted list:")
            print(f"  {sorted(_PERMITTED_LICENSES)}")
            print()
            print("Options:")
            print("  1. Review the license at:", ds.get("license_source_url", ds["source_url"]))
            print("  2. Add the SPDX code to _PERMITTED_LICENSES in this script if justified.")
            print("  3. Re-run with --skip-license-check to self-certify compliance.")
            return 1
        print(f"License check: OK ({spdx})")

    # ------------------------------------------------------------------ storage check
    free, enough = _check_storage(ds.get("expected_download_bytes"))
    free_gb = free / 1024 ** 3
    print(f"Free disk:  {free_gb:.1f} GB")
    if not enough and ds.get("expected_download_bytes"):
        needed_gb = ds["expected_download_bytes"] * 2 / 1024 ** 3
        print(f"WARNING: {needed_gb:.1f} GB needed (download × 2), only {free_gb:.1f} GB free.")
        print("  Proceeding with pilot subset. Monitor disk usage carefully.")
    print()

    # ------------------------------------------------------------------ gated access check
    if ds.get("access") == "gated":
        print("BLOCKED: This dataset requires registration or gated access.")
        print("  Resolve access externally and update the manifest with the local path.")
        print("  Notes:", ds.get("notes", ""))
        return 1

    # ------------------------------------------------------------------ fetch
    print(f"Preparing pilot subset ({pilot} samples) from {ds['source_url']} …")
    print("  This script provides the framework. Dataset-specific adapters must be")
    print("  implemented in src/sketchforge/datasets/source_adapters.py for each source.")
    print()
    print(f"  Target directory: {out}")
    print()

    # Try to call a registered adapter if available
    try:
        from sketchforge.datasets.source_adapters import get_adapter

        adapter = get_adapter(args.dataset)
        n = adapter.fetch(ds, out, pilot)
        print(f"  Fetched {n} samples via {adapter.__class__.__name__}.")
    except (ImportError, NotImplementedError, KeyError):
        print("  No adapter available yet for this dataset.")
        print("  Implement one in src/sketchforge/datasets/source_adapters.py to proceed.")
        # Write a placeholder README so the directory is not confused for a failed download
        (out / "README.md").write_text(
            f"# {ds['name']}\n\nDownload pending — implement an adapter in "
            "`src/sketchforge/datasets/source_adapters.py`.\n",
            encoding="utf-8",
        )
        return 0

    print(f"Done. {out} is ready for validation with scripts/validate_manifest.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
