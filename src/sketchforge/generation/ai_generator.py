"""AI-driven project file generator.

Replaces the template-only ``studio_generator`` path when a model provider is
available.  It asks the LLM to produce every file for the project in one shot,
streams back progress messages, and writes the result to disk.  On failure it
falls back transparently to the template generator so the UI always gets a
usable project.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are SketchForge Studio, an expert full-stack web app generator.
Given a short product brief, produce a complete, self-contained project as JSON.

Return ONLY a JSON object with this schema (no markdown fences, no explanation):
{
  "name": "<short app name>",
  "files": [
    {"path": "<relative path>", "content": "<file content as a string>"},
    ...
  ]
}

Rules:
- Generate at minimum: index.html (redirect), home.html (main page), projects.html,
  css/style.css, js/home.js, js/projects.js
- When a backend is requested also generate: backend/schema.sql, backend/models.py,
  backend/database.py, backend/logic.py, backend/api.py (Flask CRUD REST API),
  backend/tests/test_models.py, data/.gitkeep
- The frontend JS must POST form submissions to /api/submissions (relative URL).
  It must also fetch and render existing submissions on the projects page from GET /api/submissions.
- The backend Flask API must bind to 0.0.0.0 and accept an optional --port argument.
  CORS: add Access-Control-Allow-Origin: * to every response.
- Use dark, modern aesthetics (background #111116, accent #d9ff5f, font Segoe UI).
- Generated HTML must be responsive (mobile-first).
- Do NOT reference external CDN assets; all CSS/JS must be inline or in local files.
- Keep every file content as a plain string (escape newlines as \\n if needed in JSON).
- The response must be valid JSON parseable by Python's json.loads.
"""

_USER_TMPL = """\
Product brief: {brief}
Include backend: {backend}

Generate the complete project now.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ai_generate_project(
    prompt: str,
    target: Path,
    *,
    include_backend: bool = True,
    progress: Callable[[str], None] | None = None,
) -> Path | None:
    """
    Ask the LLM to generate a full project and write it to *target/<slug>/*.

    Returns the project root Path on success, None on failure (caller should
    fall back to the template generator).
    """
    def _emit(msg: str) -> None:
        log.info("ai_generate: %s", msg)
        if progress:
            progress(msg)

    _emit("Connecting to AI service...")
    try:
        client = _make_client()
    except Exception as exc:  # noqa: BLE001
        _emit(f"AI service unavailable ({exc}); using template generator.")
        return None

    _emit("Sending design brief to the model...")
    user_msg = _USER_TMPL.format(brief=prompt.strip(), backend="yes" if include_backend else "no")

    from sketchforge.integrations.provider_interface import ChatMessage, CompletionRequest

    request = CompletionRequest(
        messages=(
            ChatMessage(role="system", content=_SYSTEM),
            ChatMessage(role="user", content=user_msg),
        ),
        purpose="studio_generate",
        max_tokens=6000,
        temperature=0.4,
    )

    try:
        result = client.complete(request)
    except Exception as exc:  # noqa: BLE001
        _emit(f"Model request failed ({exc}); using template generator.")
        return None

    _emit("Parsing model response...")
    try:
        data = _parse_response(result.text)
    except ValueError as exc:
        _emit(f"Could not parse model output ({exc}); using template generator.")
        return None

    app_name = data.get("name") or " ".join(prompt.split()[:3]).title() or "New App"
    slug = re.sub(r"[^a-z0-9]+", "-", app_name.lower()).strip("-")[:48] or "new-app"
    root = target.resolve() / slug

    files: list[dict] = data.get("files", [])
    if not files:
        _emit("Model returned no files; using template generator.")
        return None

    _emit(f"Writing {len(files)} files to {root.name}/...")
    root.mkdir(parents=True, exist_ok=True)
    for entry in files:
        rel = entry.get("path", "").lstrip("/\\")
        content = entry.get("content", "")
        if not rel:
            continue
        dest = (root / rel).resolve()
        if not dest.is_relative_to(root.resolve()):
            log.warning("Ignoring model-generated path outside the project: %s", rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(str(content), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not write %s: %s", dest, exc)

    if include_backend and not (root / "requirements.txt").exists():
        (root / "requirements.txt").write_text("Flask>=3.0\n", encoding="utf-8")

    # Guarantee an entry point exists
    _ensure_entry(root)
    _emit(f"AI generation complete: {root.name} ({len(files)} files).")
    return root


def ai_revise_project(
    project_root: Path,
    instruction: str,
    *,
    progress: Callable[[str], None] | None = None,
) -> bool:
    """
    Ask the LLM to apply a follow-up instruction to an already-generated project.

    Returns True when files were updated, False on any failure.
    """
    def _emit(msg: str) -> None:
        log.info("ai_revise: %s", msg)
        if progress:
            progress(msg)

    _emit("Loading existing project files...")
    existing = _read_project(project_root)
    if not existing:
        _emit("No readable files found in the project.")
        return False

    _emit("Sending revision instruction to the model...")
    try:
        client = _make_client()
    except Exception as exc:  # noqa: BLE001
        _emit(f"AI service unavailable ({exc}).")
        return False

    revise_system = (
        _SYSTEM + "\n\nYou will receive the current project files and a revision instruction. "
        "Return ONLY a JSON object with the same schema, containing ONLY files that changed."
    )
    files_summary = json.dumps(
        [{"path": p, "content": c[:400] + "..." if len(c) > 400 else c}
         for p, c in list(existing.items())[:12]]
    )
    user_msg = (
        f"Current project files (truncated):\n{files_summary}\n\n"
        f"Revision instruction: {instruction.strip()}"
    )

    from sketchforge.integrations.provider_interface import ChatMessage, CompletionRequest

    request = CompletionRequest(
        messages=(
            ChatMessage(role="system", content=revise_system),
            ChatMessage(role="user", content=user_msg),
        ),
        purpose="studio_revise",
        max_tokens=4000,
        temperature=0.3,
    )

    try:
        result = client.complete(request)
    except Exception as exc:  # noqa: BLE001
        _emit(f"Revision request failed ({exc}).")
        return False

    _emit("Applying changes...")
    try:
        data = _parse_response(result.text)
    except ValueError as exc:
        _emit(f"Could not parse model response ({exc}).")
        return False

    files = data.get("files", [])
    updated = 0
    for entry in files:
        rel = entry.get("path", "").lstrip("/\\")
        content = entry.get("content", "")
        if not rel:
            continue
        dest = (project_root / rel).resolve()
        if not dest.is_relative_to(project_root.resolve()):
            log.warning("Ignoring model-generated revision path outside the project: %s", rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(str(content), encoding="utf-8")
            updated += 1
        except OSError as exc:
            log.warning("Could not write %s: %s", dest, exc)

    _emit(f"Revision applied: {updated} file(s) updated.")
    return updated > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client():
    """Build and return a NebiusClient with the API key from the environment."""
    from sketchforge.integrations.nebius.client import NebiusClient
    from sketchforge.integrations.nebius.configuration import load_nebius_config
    from sketchforge.integrations.nebius.request_policy import ConsentGate

    config = load_nebius_config(overrides={"enabled": True, "timeout_s": 90.0, "max_retries": 1})
    consent = ConsentGate(consented=True)
    return NebiusClient(config, consent)


def _parse_response(text: str) -> dict:
    """Extract and parse the JSON object from the model's response text."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in model response")
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc


def _read_project(root: Path) -> dict[str, str]:
    """Read all text files in the project (limited to avoid huge payloads)."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in {".html", ".css", ".js", ".py", ".sql", ".md", ".json"}:
            try:
                out[str(path.relative_to(root))] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    return out


def _ensure_entry(root: Path) -> None:
    """Make sure at least an index.html redirect exists."""
    index = root / "index.html"
    if not index.exists():
        home = root / "home.html"
        target = "home.html" if home.exists() else "index.html"
        index.write_text(
            f'<!doctype html><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url={target}">'
            f'<title>Opening app...</title><a href="{target}">Open the app</a>',
            encoding="utf-8",
        )
