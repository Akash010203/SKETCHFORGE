# Hybrid Architecture Audit: SketchForge

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`  
**Status**: Read-Only Comprehensive Audit (No source code modified)

---

## 1. Executive Summary

SketchForge was conceived as a local-first desktop workbench with a closed feedback loop:
$$\text{Sketch} \longrightarrow \text{Design IR} \longrightarrow \text{Measurement} \longrightarrow \text{Diagnosis} \longrightarrow \text{Patch} \longrightarrow \text{Verification}$$

The workspace currently houses two concurrent frontend and generation paradigms:
1. **The Desktop Workbench (`PySide6` GUI)**: A fully functional local-first desktop application (`python -m sketchforge gui`) executing local OpenCV image processing, contour/shape analysis, Design IR compilation, deterministic rendering, SVG/HTML/CSS/PNG export, WCAG and layout issue evaluation, and local geometric auto-repair. It also features a natural-language "Ask" assistant with a local intent parser and an optional model-proposer interface.
2. **The Web Studio (`web_studio.py`)**: A browser-based IDE (`python -m sketchforge studio`, port 8000) inspired by modern web studios (with topbar, artboard iframe preview, prompt input bar, example starters, media attachments, and project export). It attempts to connect hosted NVIDIA Nemotron inference via Nebius Token Factory to generate full-stack web projects.

### Core Architecture Finding
The repository does **not** have a unified control plane linking the local AI system and the hosted LLM. Instead:
- In the **Desktop Workbench**, local AI is paramount, and hosted Nemotron is treated as an optional fallback proposer (`assist/model_planner.py`).
- In the **Web Studio**, the generator (`generation/studio_generator.py` $\to$ `generation/ai_generator.py`) bypasses the local vision pipeline, layout engine, Design IR, and repair loop almost entirely, sending a raw text prompt directly to Nebius Nemotron.
- When an image is uploaded to Web Studio, an ad-hoc endpoint (`/api/sketch-analysis`) runs OpenCV `analyze()`, converts detections to plain text percentages, and tacks them onto the text prompt. It does **not** construct a `DesignDocument`, does **not** run the evaluator, and does **not** run visual discrepancy analysis.

---

## 2. System Architecture: Intended vs Reality

### Intended Architecture
```text
                    USER
                     │
                     ▼
             SKETCHFORGE STUDIO (Desktop GUI or Web Studio)
                     │
                     ▼
          SINGLE PYTHON BACKEND / ORCHESTRATOR
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
    OWN AI SYSTEM          NEMOTRON VIA NEBIUS
    (OpenCV, Layout,       (AppSpec Planning,
     Evaluator, Repair)     Code Gen, Semantics)
         │                       │
         └───────────┬───────────┘
                     ▼
          STRUCTURED APPLICATION SPEC (AppSpec)
                     │
                     ▼
            FULL-STACK GENERATION
                     │
                     ▼
          AUTOMATED VERIFICATION LOOP
          (Sandbox Execution + Screenshot + Discrepancy Analysis)
                     │
                     ▼
            VERIFIED DELIVERABLE
```

### Current Reality
```text
[Desktop GUI] ──> AppController ──> sketch_workflow.py ──> Pure Local OpenCV + IR + Local Repair
                                                          (Nemotron barely used)

[Web Studio] ──> StudioServer (/api/generate)
                        │
                        ▼
               studio_generator.py
                        │
                        ▼
               ai_generator.py ──> Nebius Nemotron
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
    Stage 1: AppSpec        Stage 2: 12 sequential calls
       (Succeeds)          (Fails on cutoffs/empty replies)
                                    │
                                    ▼
                         100% Discarded on 1 error!
                                    │
                                    ▼
                        Falls back to static template
```

---

## 3. End-to-End Trace of User Request

### A. Web Studio Request Trace (`POST /api/generate`)
1. **Frontend**: User enters prompt into `#prompt` textarea and clicks submit in `studio.js`.
2. **HTTP Dispatch**: `studio.js` dispatches `POST /api/generate` with payload `{"prompt": "<text>"}`.
3. **Studio Handler**: `StudioHandler.do_POST()` receives request, generates job ID (`uuid.uuid4().hex[:12]`), stores `_JOBS[job_id] = {"status": "running", "progress": "Starting generation…"}`, and starts daemon thread running `self._generate(job_id, prompt)`.
4. **Immediate Response**: Studio returns HTTP 202 `{"id": "<job_id>"}`.
5. **Background Thread**: `_generate` invokes `generate_studio_project(prompt, output/projects, progress=...)`.
6. **AI Generator Call**: `studio_generator.py` invokes `ai_generate_project(prompt, ...)`.
7. **Client Initialization**: `_make_client()` loads Nebius configuration with `overrides={"enabled": True, "timeout_s": 35.0, "max_retries": 1}`.
8. **Stage 1 (AppSpec Plan)**: Iterates over candidate models:
   - `nvidia/nemotron-3-super-120b-a12b`
   - `nvidia/Nemotron-3_5-Lightning`
   - `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
   Emits: `Stage 1 — requesting AppSpec plan from <model>…`
   Sends request via `NebiusClient.complete()`.
9. **Stage 2 (File Generation)**: Prepares manifest of 12 files:
   - `index.html`, `css/style.css`
   - `home.html`, `projects.html`, `js/home.js`, `js/projects.js`
   - `backend/schema.sql`, `backend/models.py`, `backend/database.py`, `backend/logic.py`, `backend/api.py`, `requirements.txt`
   Sequentially prompts Nemotron for each file individually with `max_tokens=4096`.
10. **The Fatal Breakdown**: If any single file returns empty content or reaches `max_tokens` (causing an unparseable response), the file is skipped. Because `written != len(manifest)`, `ai_generate_project` executes:
    `log.warning("Discarding incomplete AI project %s (%d file(s) missing).", root, missing)`
    and returns `None`!
11. **Silent Fallback**: `studio_generator.py` catches nothing, falls back to the static template generator, and writes pre-canned templates.
12. **Server Launch**: `_start_project_preview` spins up a loopback Python `BackendServer` subprocess and HTTP project server on a random port.
13. **Frontend Display**: `studio.js` polling `/api/jobs/<job_id>` receives `status="complete"`, creates an `<iframe>` pointing to `/preview/<slug>/home.html`.

---

## 4. Why the User Sees "Stage 1 — requesting AppSpec plan from Nemotron..." Repeatedly

Our investigation revealed three distinct mechanisms contributing to this symptom:

1. **Candidate Model Retry Flapping**:
   In `_stage1_plan()`, if model 0 fails (e.g. rate limit, timeout, or transient network hiccup), `ai_generator.py` emits:
   `emit(f"Stage 1 with {model} unavailable ({exc}); trying candidate model…")`
   and immediately executes:
   `emit(f"Stage 1 — requesting AppSpec plan from {model}…")` for model 1.
   Because `studio.js` polls only once every 900 ms, the transient failure message is overwritten almost instantly by the next model's Stage 1 message. To the user, the progress text appears frozen or repeating.

2. **Frontend Polling & Log Accumulation**:
   In `studio.js`, `addLog(job.progress)` prepends log messages to `#agent-log` only when `job.progress !== lastLoggedMessage`. Because each attempt generates a variant of `Stage 1 — requesting AppSpec plan from nvidia/...`, multiple Stage 1 entries fill the log.

3. **Total AI Project Discard Leading to User Re-submission**:
   When Stage 2 discards an incomplete project (e.g. 10/12 files generated), the user sees the template app instead of the requested AI app, prompting them to type another prompt or click an example again. This re-triggers Stage 1 repeatedly.

---

## 5. Port Allocations and Process Isolation

| Component | Default Host / Port | Implementation | Notes |
|---|---|---|---|
| Web Studio Control Plane | `127.0.0.1:8000` | `ThreadingHTTPServer` in `ui/web_studio.py` | Serves studio UI, proxies API requests |
| Generated App Preview Server | Dynamic ephemeral port | `ThreadingHTTPServer` (`ProjectHandler`) | Serves generated HTML/CSS/JS |
| Generated Backend API | Dynamic ephemeral port | `BackendServer` (`backend.api`) | Subprocess Flask REST service |
| Desktop Workbench | Local Process (no socket) | `PySide6` (`QApplication`) | True local-first desktop application |
