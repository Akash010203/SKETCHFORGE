# SKETCHFORGE — EXECUTIVE SUMMARY AUDIT REPORT

**Date:** October 24, 2026  
**Auditor:** Principal Software & AI Systems Engineer  
**Target Systems:** SketchForge Desktop Workbench, Web Studio Control Plane, Nebius × NVIDIA Inference Engine, OpenCV 5 Vision Pipeline, Full-Stack Generation Pipeline  

---

## 1. High-Level Verdict: What Was Actually Wrong

When a user submits a prompt in SketchForge Web Studio, the application appears to hang while the Agent Log repeatedly outputs:
> `"Stage 1 — requesting AppSpec plan from Nemotron…"`

Our deep code inspection and live runtime probe revealed **four intersecting root causes** supported by hard repository evidence:

### 1.1 Root Cause A: Frontend Polling Duplicate Log Spam
- **Evidence:** In `src/sketchforge/ui/web_studio/studio.js` (lines 217–224), the frontend runs a polling loop every 900 ms (`setInterval(..., 900)`). On every poll tick, it unconditionally executed `if (job.progress) addLog(job.progress)`.
- **Symptom:** Because `addLog` prepends `text + '\n'` to `log.textContent`, any slow or retried background stage dumps dozens or hundreds of identical progress strings into the UI log. The user sees a frantic flood of "Stage 1" messages and concludes the system is stuck in an infinite loop.

### 1.2 Root Cause B: Nebius Model Outage / Overload (503 / 529) and Hardcoded Model Selection
- **Evidence:** `src/sketchforge/generation/ai_generator.py` hardcoded `_NEMOTRON_MODEL = "nvidia/Nemotron-3_5-Lightning"`. Live probes against `https://api.tokenfactory.nebius.com/v1/` returned:
  - `HTTP/1.1 503 Service Temporarily Unavailable` on `nvidia/Nemotron-3_5-Lightning`
  - `HTTPError 529: {"error": {"type": "server_error", "message": "System is overloaded"}}`
- **Symptom:** Meanwhile, `nvidia/nemotron-3-super-120b-a12b` on Nebius was completely operational (returning HTTP 200 in 700 ms), but was never tried because `ai_generator.py` ignored candidate models and hardcoded `Nemotron-3_5-Lightning`.
- **Compounding Factor:** The client was configured with a 90-second timeout and 1 retry. When the primary model is overloaded, the system waited up to 180 seconds before failing and falling back to templates, during which 200 duplicate log messages flooded the screen.

### 1.3 Root Cause C: Reasoning Token Truncation (`max_tokens=512`)
- **Evidence:** When `nemotron-3-super-120b-a12b` was invoked for Stage 1, it returned internal reasoning tokens (`reasoning_tokens`). In `ai_generator.py`, `max_tokens` was capped at 512.
- **Symptom:** The token limit was reached mid-response (`finish_reason == "length"`). `NebiusClient._parse()` raised `ProviderBadResponse: the answer was cut off (max_tokens reached); it would not be valid JSON`, triggering immediate fallback.

### 1.4 Root Cause D: Dropped Security Token Causing 401 Unauthorized in Preview Proxy
- **Evidence:** Even when full-stack projects generated successfully (via AI or template fallback), the generated Flask backend (`backend/api.py`) enforced a session token check:
  ```python
  supplied = request.headers.get("X-Studio-Token", "")
  if not supplied or supplied != _STUDIO_TOKEN:
      return jsonify(error="unauthorized"), 401
  ```
  However, in `src/sketchforge/ui/web_studio.py`:
  - `ProjectHandler._handle` (line 317) proxied `/api/*` requests **without** attaching `X-Studio-Token`.
  - `StudioHandler._proxy_api` (line 204) also proxied `/api/*` requests **without** attaching `X-Studio-Token`.
- **Symptom:** Every form submission and data fetch inside the preview iframe failed with `HTTP 401 Unauthorized`. Users saw: `"Could not save: backend unavailable (HTTP 401)"`.

---

## 2. Readiness Matrix

| Dimension | Current State | Release Readiness |
|---|---|---|
| **OpenCV 5 Core Vision** | Illumination flattening, contour hierarchy, and synthetic F1 (0.982) working; grid-paper suppression active | **Ready for clean/white paper; grid paper guarded** |
| **Desktop Workbench (PySide6)** | 9/9 UI smoke tests passing offscreen; interactive canvas & undo stack verified | **Production Ready** |
| **Web Studio Control Plane** | Local HTTP server at port 8000; device previews (Desktop/Tablet/Mobile) working | **Ready with token proxy fix** |
| **Nebius AI Integration** | Token Factory client functional; verified with `nvidia/nemotron-3-super-120b-a12b` (HTTP 200) | **Ready with candidate model fallback** |
| **Full-Stack App Generation** | Emits HTML5, CSS3, ES6 JS, Python Flask, SQLite schema, CRUD endpoints, and tests | **Verified Working (passes pytest in sandbox)** |
| **Automated Test Suite** | 357 passed / 0 failed / 0 skipped | **100% Pass Rate** |
