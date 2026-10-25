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

import datetime as _dt
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


def _ts() -> str:
    """Return a compact HH:MM:SS timestamp string for progress messages."""
    return _dt.datetime.now().strftime("%H:%M:%S")


def _select_active_model(
    client,
    emit,
    *,
    ping_max_tokens: int = 8,
) -> tuple[str | None, str | None]:
    """Probe each candidate model with a trivial 1-token request.

    Returns ``(model_id, None)`` for the first responding model, or
    ``(None, last_error_str)`` when all candidates are unreachable.

    A single ``emit()`` call is made for each probe attempt so the browser
    always shows the *latest* stable state without oscillating — the caller
    does NOT emit anything before calling this function.
    """
    from sketchforge.integrations.provider_interface import ChatMessage, CompletionRequest

    last_err: str | None = None
    for idx, model in enumerate(_CANDIDATE_MODELS, start=1):
        short = model.split("/")[-1]
        emit(f"[{_ts()}] Stage 1 — verifying model {idx}/{len(_CANDIDATE_MODELS)}: {short}…")
        ping = CompletionRequest(
            messages=(
                ChatMessage(role="user", content="ping"),
            ),
            purpose="studio_plan",
            max_tokens=ping_max_tokens,
            temperature=0.0,
            model=model,
        )
        try:
            client.complete(ping)
            emit(f"[{_ts()}] Stage 1 — model ready: {short}")
            return model, None
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            log.warning("Model probe failed for %s — %s", model, exc)
            emit(
                f"[{_ts()}] Stage 1 — {short} unavailable "
                f"({type(exc).__name__}: {exc}); "
                f"{'trying next candidate…' if idx < len(_CANDIDATE_MODELS) else 'no more candidates.'}"
            )
    return None, last_err

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
- Keep the JSON under 500 tokens.
- At minimum include a "home" page and one entity if a backend is requested.
- The response MUST be valid JSON parseable by Python's json.loads.

Sketch layout rules (apply when the brief contains a <SketchDesignDocument> block):
- The block contains a "layout_block" sub-object with:
    "canvas"     — design canvas size in design pixels.
    "app_spec"   — a heuristic AppSpec already derived from the sketch.
    "components" — a flat list with id, type, parent_id, bbox_design_px (x/y/w/h),
                   label text, and confidence for every detected component.
    "hierarchy"  — a human-readable indented tree of component nesting.
- Use the "app_spec.pages" array to determine the page structure.
  Confirm and enrich the page names, titles, and routes.
- Use the "app_spec.entities" array for entity and field names.
- Use component types to infer the UI:
    "button" → ActionSpec (action=submit_form if inputs present, else navigate)
    "input"  → FieldSpec with the component's label text if present.
    "header" / "footer" / "sidebar" → structural layout containers (not entities).
    "card"   → repeating list item or data panel.
    "image"  → media content section.
- The RETURNED JSON "pages" must reflect the number of distinct top-level
  regions/flows detected (not arbitrarily invent new pages).
- If the layout_block is missing or empty, fall back to inferring from
  the legacy "regions" array (x/y/w/h in % of canvas).
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

Return the file content inside a single markdown code fence — NO JSON envelope, no extra explanation:

```<lang>
<full file content here>
```

Use the correct language tag (e.g. python, html, css, js, sql, text).

Rules:
- Use dark, modern aesthetics (background #111116, accent #d9ff5f, font Segoe UI).
- Generated HTML must be responsive (mobile-first).
- The Flask backend must bind to 0.0.0.0 and accept --port argument; add CORS header.
- Frontend JS POSTs to /api/submissions; GETs from /api/submissions for list pages.
- Do NOT reference external CDN assets; all CSS/JS must be inline or in local files.
- Output ONLY the code fence — do not wrap it in JSON or add any other text.
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
    skipped: list[str] = []
    for path_hint, description in manifest:
        _emit(f"  Generating {path_hint} ({written + len(skipped) + 1}/{len(manifest)})…")
        content = _stage2_file(client, spec_str, path_hint, description, _emit, model=active_model or _NEMOTRON_MODEL)
        if content is None:
            log.warning("Skipping %s — model returned no content.", path_hint)
            skipped.append(path_hint)
            continue
        dest = (root / path_hint).resolve()
        if not dest.is_relative_to(root):
            log.warning("Ignoring model-generated path outside the project: %s", path_hint)
            skipped.append(path_hint)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(str(content), encoding="utf-8")
            written += 1
        except OSError as exc:
            log.warning("Could not write %s: %s", dest, exc)
            skipped.append(path_hint)

    if written == 0:
        # Nothing usable at all — fall back to the template generator.
        _emit("AI generation produced no files; using the template generator instead.")
        log.warning("Discarding empty AI project directory %s.", root)
        return None

    if skipped:
        _emit(
            f"AI generation partial ({written}/{len(manifest)} files written; "
            f"{len(skipped)} skipped: {', '.join(skipped)}). "
            "Using partial AI output — template generator will fill remaining files."
        )
        log.warning(
            "Incomplete AI project %s: %d/%d files written; skipped: %s",
            root, written, len(manifest), skipped,
        )

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
        "Return ONLY a JSON object with this schema — no extra text, no outer markdown fence:\n"
        '{"files": [{"path": "<rel path>", "content": "<full updated content>"}]}\n'
        "The value of each \"content\" field must be the raw file text as a plain string.\n"
        "If the file content is large, split it into multiple small files rather than\n"
        "producing one giant JSON string that risks being truncated.\n"
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


def _spec_from_layout_block(prompt: str) -> dict | None:
    """Extract and return a pre-seeded AppSpec dict from the SketchDesignDocument block.

    When the user uploads a sketch before generation, the frontend embeds a
    ``<SketchDesignDocument>`` XML fragment containing a ``layout_block`` with:
    - ``app_spec``   — heuristic AppSpec already derived via ``spec_from_document()``
    - ``components`` — exact design-px bboxes + containment hierarchy
    - ``hierarchy``  — human-readable tree
    - ``canvas``     — canvas dimensions

    This function extracts that ``app_spec`` sub-object and converts it into the
    flat dict format that Stage 1 returns (name, pages, entities, include_backend).
    Nemotron then enriches this grounded spec rather than inventing a layout.

    Returns None when no block is found or the block cannot be parsed.
    """
    import re

    match = re.search(r"<SketchDesignDocument>(.*?)</SketchDesignDocument>", prompt, re.DOTALL)
    if not match:
        return None
    try:
        block_json = json.loads(match.group(1).strip())
    except (ValueError, json.JSONDecodeError):
        return None

    layout_block = block_json.get("layout_block")
    if not layout_block or not isinstance(layout_block, dict):
        # Fall back to legacy regions array
        regions = block_json.get("regions", [])
        if not regions:
            return None
        # Build a minimal spec from the legacy regions list
        inputs = [r for r in regions if r.get("type") == "input"]
        buttons = [r for r in regions if r.get("type") == "button"]
        has_backend = len(inputs) >= 2 and len(buttons) >= 1
        pages = [{"name": "home", "title": "Home", "route": "/"}]
        entities = []
        if has_backend:
            entities = [{"name": "Record", "fields": [{"name": f"field_{i}", "type": "text"} for i in range(len(inputs))]}]
        return {"name": "Sketch App", "pages": pages, "entities": entities, "include_backend": has_backend}

    app_spec = layout_block.get("app_spec", {})
    if not app_spec:
        return None

    # Convert AppSpec dataclass-dict format -> Stage-1 flat format
    pages_raw = app_spec.get("pages", [])
    pages = []
    for p in pages_raw:
        pages.append({
            "name": p.get("name", "home"),
            "title": p.get("title", p.get("name", "Home").title()),
            "route": p.get("route", "/"),
        })
    if not pages:
        pages = [{"name": "home", "title": "Home", "route": "/"}]

    entities_raw = app_spec.get("entities", [])
    entities = []
    for e in entities_raw:
        fields_raw = e.get("fields", [])
        fields = [{"name": f.get("name", "field"), "type": f.get("type", "text")} for f in fields_raw]
        entities.append({"name": e.get("name", "Record"), "fields": fields})

    include_backend = bool(app_spec.get("tech_backend", "none") != "none" or entities)

    return {
        "name": app_spec.get("name", "Sketch App"),
        "pages": pages,
        "entities": entities,
        "include_backend": include_backend,
    }


def _stage1_plan(
    client,
    prompt: str,
    include_backend: bool,
    emit: Callable[[str], None],
) -> tuple[dict | None, str | None]:
    """Stage 1: request a compact AppSpec JSON from a single verified Nemotron model.

    The model is selected **once** at the start of this call via
    :func:`_select_active_model`, which probes each candidate in priority order
    and emits a timestamped status for every probe attempt.  This eliminates the
    previous flapping behaviour where:

    * ``emit("trying model 0…")`` fires,
    * model 0 fails,
    * ``emit("trying model 1…")`` immediately overwrites it,

    …so the browser (polling every 900 ms) never displayed the failure reason.

    With this approach:
    - One probe phase with timestamped per-attempt statuses.
    - On probe failure the exact exception type + message is emitted before
      falling back to the seeded spec or template generator.
    - One plan request against the verified model; on parse failure the error
      is emitted explicitly before the fallback path is taken.

    When the prompt contains a ``<SketchDesignDocument>`` block we first extract
    a pre-seeded AppSpec from the embedded ``layout_block`` (exact bbox geometry,
    containment hierarchy, and heuristic AppSpec derived by ``spec_from_document``).
    The pre-seeded spec is merged into whatever the model returns so the final
    plan is always grounded in the sketch detections, not invented by the model.
    """
    from sketchforge.integrations.provider_interface import ChatMessage, CompletionRequest

    # ------------------------------------------------------------------
    # Extract pre-seeded spec from the sketch layout block (if present).
    # ------------------------------------------------------------------
    seeded_spec = _spec_from_layout_block(prompt)
    if seeded_spec:
        log.info(
            "Stage 1: pre-seeded spec from sketch layout block — %s page(s), %s entity/entities.",
            len(seeded_spec.get("pages", [])),
            len(seeded_spec.get("entities", [])),
        )

    # ------------------------------------------------------------------
    # Probe once — select a single verified model before planning.
    # ------------------------------------------------------------------
    active_model, probe_err = _select_active_model(client, emit)

    if active_model is None:
        # All candidates unreachable — emit the failure cause explicitly.
        if seeded_spec:
            emit(
                f"[{_ts()}] Stage 1 — all models unreachable ({probe_err}); "
                "using sketch-derived layout as fallback plan."
            )
            log.warning("Stage 1 Nemotron unavailable — falling back to sketch-seeded spec.")
            seeded_spec.setdefault("include_backend", include_backend)
            return seeded_spec, None
        emit(
            f"[{_ts()}] Stage 1 — all models unreachable ({probe_err}); "
            "falling back to template generator."
        )
        return None, None

    # ------------------------------------------------------------------
    # Single plan request against the verified model.
    # ------------------------------------------------------------------
    user_msg = _PLAN_USER.format(
        brief=prompt.strip(),
        backend="yes" if include_backend else "no",
    )
    short_model = active_model.split("/")[-1]
    emit(f"[{_ts()}] Stage 1 — requesting AppSpec plan from {short_model}…")

    request = CompletionRequest(
        messages=(
            ChatMessage(role="system", content=_PLAN_SYSTEM),
            ChatMessage(role="user", content=user_msg),
        ),
        purpose="studio_plan",
        max_tokens=1536,
        temperature=0.2,
        model=active_model,
    )
    try:
        result = client.complete(request)
        spec = _parse_response(result.text)
    except Exception as exc:  # noqa: BLE001
        # Emit the actual failure cause — it will be a distinct string from the
        # previous "requesting…" message so the browser log shows both.
        failure_reason = f"{type(exc).__name__}: {exc}"
        log.warning("Stage 1 plan request with %s failed: %s", active_model, exc)
        if seeded_spec:
            emit(
                f"[{_ts()}] Stage 1 — plan request failed ({failure_reason}); "
                "using sketch-derived layout as fallback plan."
            )
            seeded_spec.setdefault("include_backend", include_backend)
            return seeded_spec, None
        emit(
            f"[{_ts()}] Stage 1 — plan request failed ({failure_reason}); "
            "falling back to template generator."
        )
        return None, None

    # ------------------------------------------------------------------
    # Merge: use the model's enriched spec but honour seeded values for
    # any field the model left empty or omitted.
    # ------------------------------------------------------------------
    if seeded_spec:
        if not spec.get("pages"):
            spec["pages"] = seeded_spec["pages"]
        if not spec.get("entities"):
            spec["entities"] = seeded_spec["entities"]
        if not spec.get("name") or spec["name"] in {"Sketch App", "GeneratedApp"}:
            spec["name"] = seeded_spec.get("name", spec.get("name", "Sketch App"))
        spec.setdefault("include_backend", seeded_spec.get("include_backend", include_backend))

    emit(
        f"[{_ts()}] Stage 1 complete — app: '{spec.get('name', '?')}', "
        f"{len(spec.get('pages', []))} page(s), "
        f"{len(spec.get('entities', []))} entity/entities."
    )
    return spec, active_model


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
        max_tokens=8192,  # raised from 4096 — api.py / projects.html regularly exceed 4 k tokens
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
    """Extract file content from a markdown code fence, JSON envelope, or raw output.

    Priority order (highest first):
      1. Markdown code fences  — the new preferred format; avoids JSON string-escaping
         and therefore never hits token limits due to backslash proliferation.
      2. JSON envelope  {"path": "...", "content": "..."}  — legacy fallback so
         responses from older model versions or cached completions still work.
      3. Raw text  — last resort when the model emits bare code with no wrapper.
    """
    if not text or not text.strip():
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL).strip()

    # 1. Markdown code fences (preferred — no JSON string-escaping overhead)
    fences = re.findall(r"```(?:[a-zA-Z0-9_\-]*)\s*\n(.*?)\n```", cleaned, re.DOTALL)
    if fences:
        return max(fences, key=len).strip()

    # 2. JSON envelope fallback {"path": "...", "content": "..."}
    try:
        data = _parse_response(cleaned)
        content = data.get("content")
        if isinstance(content, str) and content.strip():
            log.debug("_parse_file_content: fell back to JSON envelope for %s", path_hint)
            return content
    except Exception:
        pass

    # 3. Raw code content (no wrapper at all)
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        log.debug("_parse_file_content: using raw output for %s", path_hint)
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
