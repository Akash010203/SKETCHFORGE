"""Package the SketchForge application for distribution.

Supports two packaging modes:
  1. **Python wheel** (default): builds a wheel using the pyproject.toml
     configuration. Runnable on any machine with Python 3.11+.
  2. **Standalone executable** (--pyinstaller): uses PyInstaller to bundle
     all dependencies into a single-directory distribution. Requires
     ``pip install pyinstaller`` first.

Usage
-----
    # Wheel only (always works if build is installed):
    python -I scripts/package_application.py

    # Standalone executable:
    python -I scripts/package_application.py --pyinstaller

    # Specify output directory:
    python -I scripts/package_application.py --out dist/ [--pyinstaller]

The packaged application always keeps the no-API-server constraint: it
never starts a REST endpoint and only makes outbound network calls when
explicitly configured by the user.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ENTRY = "sketchforge.__main__:main"
APP_NAME = "SketchForge"


def _build_wheel(out: Path) -> int:
    """Build a Python wheel using build."""
    out.mkdir(parents=True, exist_ok=True)
    print("Building Python wheel …")
    try:
        import build  # noqa: F401 (just check availability)
    except ImportError:
        print("  Installing build backend …")
        subprocess.run([sys.executable, "-m", "pip", "install", "build", "-q"], check=True)

    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", f"--outdir={out}"],
        cwd=str(ROOT), capture_output=True, text=True
    )
    if result.returncode != 0:
        print("  FAILED:")
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
        return result.returncode

    wheels = list(out.glob("*.whl"))
    if wheels:
        print(f"  Wheel: {wheels[0].name}")
    else:
        print("  WARNING: no wheel found in output directory")
    return 0


def _build_pyinstaller(out: Path) -> int:
    """Bundle into a standalone executable using PyInstaller."""
    if shutil.which("pyinstaller") is None:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller", "-q"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print("ERROR: could not install PyInstaller automatically.")
            print("  Run: pip install pyinstaller")
            return 1

    out.mkdir(parents=True, exist_ok=True)
    spec_args = [
        "pyinstaller",
        "--name", APP_NAME,
        "--distpath", str(out),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"),
        "--onedir",                        # single-directory bundle
        "--windowed",                      # no console window on Windows
        "--noconfirm",                     # overwrite without prompting
        # Hidden imports needed for PySide6 and optional modules
        "--hidden-import", "PySide6.QtSvg",
        "--hidden-import", "PySide6.QtPrintSupport",
        "--hidden-import", "sketchforge",
        # Add assets
        f"--add-data={ROOT / 'assets'}{';' if sys.platform == 'win32' else ':'}assets",
        f"--add-data={ROOT / 'config'}{';' if sys.platform == 'win32' else ':'}config",
        # Entry point
        str(ROOT / "src" / "sketchforge" / "__main__.py"),
    ]

    print("Building standalone executable with PyInstaller …")
    print(f"  Output: {out / APP_NAME}")
    result = subprocess.run(spec_args, cwd=str(ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        print("  PyInstaller FAILED:")
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
        return result.returncode

    exe = out / APP_NAME / (APP_NAME + (".exe" if sys.platform == "win32" else ""))
    if exe.is_file():
        size_mb = exe.stat().st_size / 1024 ** 2
        print(f"  Executable: {exe}  ({size_mb:.1f} MB)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pyinstaller", action="store_true",
                    help="Build a standalone executable (requires PyInstaller)")
    ap.add_argument("--wheel", action="store_true",
                    help="Build a Python wheel (default if --pyinstaller is not given)")
    ap.add_argument("--out", default="dist",
                    help="Output directory (default: dist/)")
    args = ap.parse_args()

    out = ROOT / args.out
    t0 = time.perf_counter()
    rc = 0

    # Default: build wheel unless --pyinstaller only
    build_wheel = args.wheel or not args.pyinstaller

    if build_wheel:
        rc = _build_wheel(out / "wheel")
        if rc != 0:
            return rc

    if args.pyinstaller:
        rc = _build_pyinstaller(out / "standalone")
        if rc != 0:
            return rc

    elapsed = time.perf_counter() - t0
    print()
    print(f"Packaging complete in {elapsed:.1f}s. Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
