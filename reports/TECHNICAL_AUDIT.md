# SKETCHFORGE — TECHNICAL AUDIT REPORT

**Date:** October 24, 2026  
**Repository:** `C:\Users\akash\Downloads\sketchforge`  
**Test Baseline:** 357 Passed / 0 Failed (Python 3.11.9, OpenCV 5.0.0, PySide6 6.12.0, Windows 11 AMD64)  

---

## 1. Subsystem & Module Inventory

The repository contains **257 production Python files** across 24 modular subsystems:

```
src/sketchforge/
├── application/     # App controller, background tasks, event bus, state management
├── assist/          # Natural language edit parser, prompt planner, edit benchmarks
├── cloud/           # AWS Lambda client (AWSSketchClient) and deployment templates
├── datasets/        # Dataset loaders, adapters, normalizers (WebSight, DrawnUI, IAM)
├── design_ir/       # Pydantic schema (DesignDocument, Component, BBox, Style), AST
├── domain/          # Bounding boxes, colors, geometry primitives, invariants
├── editor/          # Command pattern undo/redo stack, selection, lock manager
├── evaluation/      # 10 layout fault detectors, WCAG contrast, fidelity metrics
├── execution/       # Command policy, sub-process sandbox, environment scrubber
├── generation/      # Two-stage AI Nemotron generator, Vite/React, Flask/SQLite
├── integrations/    # Nebius Token Factory client, ConsentGate, model registry
├── layout/          # Hierarchy inference, containment, pitch, alignment snapping
├── models/          # CNN component detector, layout segmentation, TrOCR/CRNN
├── orchestration/   # Workflow orchestrators, repair budgets, stopping rules
├── rendering/       # Deterministic SVG, HTML/CSS, and raster PNG renderers
├── repair/          # Fault diagnosis, patch candidates, regression check, rollback
├── retrieval/       # BM25 + vector hybrid search, token feature hashing
├── storage/         # Project bundle loader, atomic file storage, archive exports
├── training/        # PyTorch training loops, loss functions, checkpoint manager
├── ui/              # PySide6 Desktop GUI + Web Studio HTTP server & frontend
├── utilities/       # Timing, paths, logging, hashing, process management
├── verification/    # Project inspector, syntax check, build and type-check runner
└── vision/          # OpenCV 5 preprocessing, thresholding, contours, perspective
```

---

## 2. Request Lifecycle & Exact Failure Trace

The target workflow was traced step-by-step:

```
[1] User enters prompt in Browser Studio
    │
    ▼
[2] Browser sends POST /api/generate with JSON {"prompt": "..."}
    │
    ▼
[3] StudioHandler._generate receives request; assigns job_id; sets status="running"
    │
    ▼
[4] Orchestration calls generate_studio_project(...) in studio_generator.py
    │
    ▼
[5] generate_studio_project calls ai_generate_project(...) in ai_generator.py
    │
    ▼
[6] ai_generator.py sets progress message:
    "Stage 1 — requesting AppSpec plan from Nemotron…"
    │
    ▼
[7] NebiusClient calls POST https://api.tokenfactory.nebius.com/v1/chat/completions
    │
    ├── FAIL A: Target model (Nemotron-3_5-Lightning) returns HTTP 503 or 529.
    │   NebiusClient waits 30-90s, retries, and fails.
    │
    ├── FAIL B: UI poll loop (/api/jobs/<id>) ticks every 900 ms.
    │   Unconditionally calls addLog(job.progress), prepending duplicate
    │   "Stage 1" strings hundreds of times. User perceives hang.
    │
    ├── FAIL C: Alternate reasoning model (nemotron-3-super-120b-a12b) returns reasoning
    │   tokens, exceeding max_tokens=512. Client raises ProviderBadResponse (cut off).
    │
    ▼
[8] Stage 1 fails; pipeline drops to template fallback in studio_generator.py.
    │
    ▼
[9] Templates generate HTML5, CSS3, JS, Flask api.py, models.py, schema.sql.
    │
    ▼
[10] StudioHandler._start_project_preview launches BackendServer with STUDIO_TOKEN.
    │
    ▼
[11] Preview iframe loads http://127.0.0.1:<preview_port>/home.html.
    │
    ├── FAIL D: User fills form; home.js submits POST /api/items.
    │   ProjectHandler._handle proxies request to backend without X-Studio-Token.
    │   Generated Flask backend rejects request with HTTP 401 Unauthorized.
    │   UI displays: "Could not save: backend unavailable (HTTP 401)".
```

---

## 3. Detailed Root Causes with Code Evidence

### Defect 1: Log Flooding in `studio.js`
- **Location:** `src/sketchforge/ui/web_studio/studio.js:217–224`
- **Code:**
  ```javascript
  pollTimer = setInterval(async () => {
    const res = await fetch('/api/jobs/' + payload.id);
    const job = await res.json();
    const p = $('#progress');
    if (p) p.textContent = job.progress || 'Generating…';
    if (job.progress) addLog(job.progress); // ← SPAMS UNCONDITIONALLY EVERY 900MS
  ```
- **Correction:** Keep `let lastProgress = ""` and only invoke `addLog` when `job.progress !== lastProgress`.

### Defect 2: Nebius Model Hardcoding & 503/529 Overload
- **Location:** `src/sketchforge/generation/ai_generator.py:30`
- **Code:**
  ```python
  _NEMOTRON_MODEL = "nvidia/Nemotron-3_5-Lightning"
  ```
- **Finding:** Live Nebius Token Factory query returned `HTTP 503 Service Temporarily Unavailable` and `HTTP 529 System is overloaded` for `nvidia/Nemotron-3_5-Lightning`, while `nvidia/nemotron-3-super-120b-a12b` returned HTTP 200 in 700 ms.
- **Correction:** Implement candidate model fallback loop (`_CANDIDATE_MODELS = ("nvidia/nemotron-3-super-120b-a12b", "nvidia/Nemotron-3_5-Lightning", ...)`).

### Defect 3: Token Limit Truncation on Reasoning Models
- **Location:** `src/sketchforge/generation/ai_generator.py:331`
- **Code:**
  ```python
  request = CompletionRequest(..., max_tokens=512, model=_NEMOTRON_MODEL)
  ```
- **Finding:** NVIDIA Nemotron reasoning models generate reasoning tokens (`reasoning_tokens`) that consume token budget before the output JSON starts. With `max_tokens=512`, `finish_reason` is `"length"`.
- **Correction:** Increase Stage 1 budget to `max_tokens=1536` and Stage 2 to `max_tokens=4096`.

### Defect 4: Proxy Dropping `X-Studio-Token` (HTTP 401 Bug)
- **Location:** `src/sketchforge/ui/web_studio.py:204–206, 317–318`
- **Code:**
  ```python
  req = Request(f"http://127.0.0.1:{backend_port}{self.path}", data=body, method=self.command,
                headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
  ```
- **Finding:** `BackendServer` initializes with `child_env["STUDIO_TOKEN"] = session_token`. `api.py` checks `X-Studio-Token`. The proxy only sent `Content-Type`, stripping the session token.
- **Correction:** Forward `X-Studio-Token: backend.session_token` in both proxy handlers.
