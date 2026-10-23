"""Backend API server manager for generated projects.

When a generated project includes a Flask backend (backend/api.py), this module
starts and manages that process, serving it on a free local port. The preview
panel routes /api/* requests through this server via the iframe URL.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)


class BackendServer:
    """Manages a single subprocess running backend/api.py for a generated project."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._port: int | None = None
        self._project_root: Path | None = None
        self._lock = threading.Lock()

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self, project_root: Path) -> int | None:
        """Start the backend for *project_root*.  Returns the port, or None."""
        self.stop()
        api_script = project_root / "backend" / "api.py"
        if not api_script.is_file():
            log.debug("No backend/api.py in %s; skipping backend server.", project_root)
            return None

        port = _free_port()
        env = {**os.environ, "FLASK_ENV": "development", "PYTHONUNBUFFERED": "1"}
        try:
            proc = subprocess.Popen(
                [sys.executable, str(api_script), "--port", str(port)],
                cwd=str(project_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            log.warning("Could not start backend server: %s", exc)
            return None

        # Wait up to 5 s for the server to accept connections
        if not _wait_for_port("127.0.0.1", port, timeout=5.0):
            log.warning("Backend server did not start in time on port %d.", port)
            proc.terminate()
            return None

        with self._lock:
            self._process = proc
            self._port = port
            self._project_root = project_root

        log.info("Backend server started on port %d for %s.", port, project_root.name)
        # Drain stdout in a daemon thread so the pipe does not block.
        threading.Thread(target=_drain, args=(proc,), daemon=True, name="sketchforge-api-log").start()
        return port

    def stop(self) -> None:
        with self._lock:
            proc = self._process
            self._process = None
            self._port = None
            self._project_root = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Return an OS-assigned free TCP port."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    """Return True when something is accepting TCP connections on host:port."""
    import socket
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _drain(proc: subprocess.Popen) -> None:
    """Read and log stdout/stderr from the backend process."""
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            log.debug("[backend] %s", line.rstrip())
    except Exception:  # noqa: BLE001
        pass
