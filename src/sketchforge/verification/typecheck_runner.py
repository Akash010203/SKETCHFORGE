"""Typecheck runner stub — wraps tsc --noEmit in a VerificationStep."""
from __future__ import annotations

import time
from pathlib import Path

from sketchforge.execution.sandbox import SandboxSession
from sketchforge.verification.verification_report import VerificationStep


def run_typecheck(session: SandboxSession, project_root: Path) -> VerificationStep:
    t0 = time.perf_counter()
    r = session.run(["npx", "tsc", "--noEmit"], cwd=project_root, timeout=60)
    return VerificationStep(
        name="tsc --noEmit",
        ok=r.ok,
        duration_ms=(time.perf_counter() - t0) * 1000,
        stdout=r.stdout,
        stderr=r.stderr,
        returncode=r.returncode,
    )
