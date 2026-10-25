"""AI-driven project file generator — Two-Stage Generation Pipeline.

Stage 1 (Plan & Architecture): Sends a lean prompt to nvidia/Nemotron-3_5-Lightning
  requesting only the AppSpec JSON (~500 tokens).  The AppSpec captures app name,
  pages, entities, field definitions, and route definitions.

Stage 2 (File Generation): Using the confirmed AppSpec, prompts the model to generate
  each dynamic file (frontend/home.js, backend/logic.py, backend/schema.sql, …)
  individually with a bounded 2,048-token cap per request, then merges all files into
  the project folder.

On any failure the pipeline falls back transparently to the template generator so the
UI always gets a usable project.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model selection: candidate priority order
# ---------------------------------------------------------------------------

_CANDIDATE_MODELS = (
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/Nemotron-3_5-Lightning",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
)
_NEMOTRON_MODEL = _CANDIDATE_MODELS[0]

# ---------------------------------------------------------------------------
# Stage-1 prompt: AppSpec plan
# ---------------------------------------------------------------------------

_PLAN_SYSTEM = """\
You are SketchForge Studio's architecture planner.
Given a short product brief, produce ONLY a compact JSON AppSpec.

Return ONLY a JSON object — no markdown fences, no explanation:
{
  "name": "<short app name>",
  "pages": [
    {"name": "<page_slug>", "title": "<Page Title>", "route": "/<slug>"}
  ],
  "entities": [
    {
      "name": "<EntityName>",
      "fields": [
        {"name": "<field>", "type": "<text|int|bool|float|date>"}
      ]
    }
  ],
  "include_backend": true
}

Rules:
- Keep the JSON under 400 tokens.
- At minimum include a "home" page and one entity if a backend is requested.
- The response MUST be valid JSON parseable by Python's json.loads.
"""

_PLAN_USER = """\
Product brief: {brief}
Include backend: {backend}

Generate the AppSpec plan now.
"""

# ---------------------------------------------------------------------------
# Stage-2 prompt: individual file generation
# ---------------------------------------------------------------------------

_FILE_SYSTEM = """\
You are SketchForge Studio's code generator.
Generate exactly ONE file based on the AppSpec and the file path given below.

Return ONLY a JSON object — no markdown fences, no explanation:
{"path": "<relative/path/to/file>", "content": "<full file content as a string>"}

Rules:
- Use dark, modern aesthetics (background #111116, accent #d9ff5f, font Segoe UI).
- Generated HTML must be responsive (mobile-first).
- The Flask backend must bind to 0.0.0.0 and accept --port argument; add CORS header.
- Frontend JS POSTs to /api/submissions; GETs from /api/submissions for list pages.
- Do NOT reference external CDN assets; all CSS/JS must be inline or in local files.
- Keep file content as a plain string (escape newlines as \\n in JSON if needed).
- The response MUST be valid JSON parseable by Python's json.loads.
"""

_FILE_USER = """\
AppSpec:
{spec}

Generate this file now:
Path: {path}
Description: {description}
"""

# ---------------------------------------------------------------------------
# File manifest derived from AppSpec
# ---------------------------------------------------------------------------

_STATIC_FILES = [
    ("index.html", "Root redirect page (meta-refresh to home.html)"),
    ("css/style.css", "Dark-themed responsive stylesheet (bg #111116, accent #d9ff5f)"),
]

_FRONTEND_FILES = [
    ("home.html", "Main landing page using the app name and entities"),
    ("projects.html", "List page that GETs /api/submissions and renders items"),
    ("js/home.js", "Form submission logic — POSTs to /api/submissions"),
    ("js/projects.js", "Fetch and render submissions from GET /api/submissions"),
]

_BACKEND_FILES = [
    ("backend/schema.sql", "SQLite CREATE TABLE statements for every entity"),
    ("backend/models.py", "Python dataclass models for every entity"),
    ("backend/database.py", "SQLite connection helper with schema init on first run"),
    ("backend/logic.py", "Business logic functions (CRUD) for every entity"),
    ("backend/api.py", "Flask CRUD REST API, bound to 0.0.0.0 with --port arg and CORS"),
    ("requirements.txt", "Flask>=3.0 and any other needed packages, one per line"),
]


def _file_manifest(spec: dict) -> list[tuple[str, str]]:
    """Return (path, description) tuples for every file to generate."""
    files = list(_STATIC_FILES) + list(_FRONTEND_FILES)
    if spec.get("include_backend", True):
        files += list(_BACKEND_FILES)
    return files


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
    Two-stage AI generation pipeline:
      1. Plan  – ask the model for a compact AppSpec (~500 tokens).
      2. Files – generate each dynamic file individually (≤2,048 tokens each).

    Returns the project root Path on success, None on failure (caller should
    fall back to the template generator).
    """
    def _emit(msg: str) -> None:
        log.info("ai_generate: %s", msg)
        if progress:
            progress(msg)

    _emit("Connecting to AI service…")
    try:
        client = _make_client()
    except Exception as exc:  # noqa: BLE001
        _emit(f"AI service unavailable ({exc}); using template generator.")
        return None

    # ------------------------------------------------------------------
    # Stage 1 — AppSpec plan
    # ------------------------------------------------------------------
    spec, active_model = _stage1_plan(client, prompt, include_backend, _emit)
    if spec is None:
        return None

    app_name = spec.get("name") or " ".join(prompt.split()[:3]).title() or "New App"
    slug = re.sub(r"[^a-z0-9]+", "-", app_name.lower()).strip("-")[:48] or "new-app"
    root = target.resolve() / slug
    root.mkdir(parents=True, exist_ok=True)

    spec_str = json.dumps(spec, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Stage 2 — per-file generation
    # ------------------------------------------------------------------
    manifest = _file_manifest(spec)
    _emit(f"Stage 2 — generating {len(manifest)} files individually…")

    written = 0
    for path_hint, description in manifest:
        _emit(f"  Generating {path_hint}…")
        content = _stage2_file(client, spec_str, path_hint, description, _emit, model=active_model or _NEMOTRON_MODEL)
        if content is None:
            log.warning("Skipping %s — model returned no content.", path_hint)
            continue
        dest = (root / path_hint).resolve()
        if not dest.is_relative_to(root):
            log.warning("Ignoring model-generated path outside the project: %s", path_hint)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(str(content), encoding="utf-8")
            written += 1
        except OSError as exc:
            log.warning("Could not write %s: %s", dest, exc)

    if written != len(manifest):
        missing = len(manifest) - written
        _emit(f"AI generation was incomplete ({written}/{len(manifest)} files); "
              f"using the complete template generator instead.")
        log.warning("Discarding incomplete AI project %s (%d file(s) missing).", root, missing)
        return None

    _ensure_entry(root)
    _emit(f"AI generation complete: {root.name} ({written}/{len(manifest)} files).")
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

    _emit("Loading existing project files…")
    existing = _read_project(project_root)
    if not existing:
        _emit("No readable files found in the project.")
        return False

    _emit("Sending revision instruction to the model…")
    try:
        client = _make_client()
    except Exception as exc:  # noqa: BLE001
        _emit(f"AI service unavailable ({exc}).")
        return False

    revise_system = (
        "You are SketchForge Studio's revision assistant.\n"
        "You will receive the current project files (truncated) and a revision instruction.\n"
        "Return ONLY a JSON object with this schema — no markdown fences, no explanation:\n"
        '{"files": [{"path": "<rel path>", "content": "<full updated content>"}]}\n'
        "Include ONLY files that need to change. The JSON must be parseable by json.loads."
    )
    files_summary = json.dumps(
        [{"path": p, "content": c[:400] + "…" if len(c) > 400 else c}
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
        max_tokens=2048,
        temperature=0.3,
        model=_NEMOTRON_MODEL,
    )

    try:
        result = client.complete(request)
    except Exception as exc:  # noqa: BLE001
        _emit(f"Revision request failed ({exc}).")
        return False

    _emit("Applying changes…")
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
# Stage helpers
# ---------------------------------------------------------------------------


def _stage1_plan(
    client,
    prompt: str,
    include_backend: bool,
    emit: Callable[[str], None],
) -> tuple[dict | None, str | None]:
    """Stage 1: request a compact AppSpec JSON from an available NVIDIA Nemotron model."""
    from sketchforge.integrations.provider_interface import ChatMessage, CompletionRequest

    user_msg = _PLAN_USER.format(
        brief=prompt.strip(),
        backend="yes" if include_backend else "no",
    )

    last_exc = None
    for model in _CANDIDATE_MODELS:
        emit(f"Stage 1 — requesting AppSpec plan from {model}…")
        request = CompletionRequest(
            messages=(
                ChatMessage(role="system", content=_PLAN_SYSTEM),
                ChatMessage(role="user", content=user_msg),
            ),
            purpose="studio_plan",
            max_tokens=1536,
            temperature=0.2,
            model=model,
        )
        try:
            result = client.complete(request)
            spec = _parse_response(result.text)
            emit(f"Stage 1 complete ({model}) — app: '{spec.get('name', '?')}', "
                 f"{len(spec.get('pages', []))} page(s), "
                 f"{len(spec.get('entities', []))} entity/entities.")
            return spec, model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Stage 1 attempt with %s failed: %s", model, exc)
            emit(f"Stage 1 with {model} unavailable ({exc}); trying candidate model…")

    emit(f"All AI candidate models unavailable ({last_exc}); using template generator.")
    return None, None


def _stage2_file(
    client,
    spec_str: str,
    path_hint: str,
    description: str,
    emit: Callable[[str], None],
    model: str = _NEMOTRON_MODEL,
) -> str | None:
    """Stage 2: generate ONE file and return its content string, or None on failure."""
    from sketchforge.integrations.provider_interface import ChatMessage, CompletionRequest

    user_msg = _FILE_USER.format(
        spec=spec_str,
        path=path_hint,
        description=description,
    )
    request = CompletionRequest(
        messages=(
            ChatMessage(role="system", content=_FILE_SYSTEM),
            ChatMessage(role="user", content=user_msg),
        ),
        purpose="studio_file",
        max_tokens=4096,
        temperature=0.2,
        model=model,
    )
    try:
        result = client.complete(request)
    except Exception as exc:  # noqa: BLE001
        log.warning("Stage 2 request for %s failed: %s", path_hint, exc)
        return None

    return _parse_file_content(result.text, path_hint)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_client():
    """Build and return a NebiusClient with the API key from the environment."""
    from sketchforge.integrations.nebius.client import NebiusClient
    from sketchforge.integrations.nebius.configuration import load_nebius_config
    from sketchforge.integrations.nebius.request_policy import ConsentGate

    config = load_nebius_config(overrides={"enabled": True, "timeout_s": 35.0, "max_retries": 1})
    consent = ConsentGate(consented=True)
    return NebiusClient(config, consent)


def _parse_file_content(text: str, path_hint: str) -> str | None:
    """Extract file content whether formatted as a JSON envelope, markdown fence, or raw code."""
    if not text or not text.strip():
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL).strip()

    # 1. Try parsing JSON envelope {"path": "...", "content": "..."}
    try:
        data = _parse_response(cleaned)
        content = data.get("content")
        if isinstance(content, str) and content.strip():
            return content
    except Exception:
        pass

    # 2. Try markdown code fences
    fences = re.findall(r"```(?:[a-zA-Z0-9_\-]+)?\s*\n(.*?)\n```", cleaned, re.DOTALL)
    if fences:
        return max(fences, key=len).strip()

    # 3. Direct raw code content
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        return cleaned

    return None


def _parse_response(text: str) -> dict:
    """Extract and parse the first JSON object from the model's response text."""
    text = text.strip()
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL).strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in model response")
    try:
        return json.loads(cleaned[start:end])
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
            f'<title>Opening app…</title><a href="{target}">Open the app</a>',
            encoding="utf-8",
        )
