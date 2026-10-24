# SKETCHFORGE — IMPLEMENTATION CHANGELOG

**Date:** October 24, 2026  
**Auditor / Principal Engineer:** Automated Audit & Repair Mission  

---

## Changes Log

### 1. `src/sketchforge/generation/ai_generator.py`
- **Change:** 
  - Defined `_CANDIDATE_MODELS = ("nvidia/nemotron-3-super-120b-a12b", "nvidia/Nemotron-3_5-Lightning", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")`.
  - Updated `_stage1_plan` to iterate through candidate models if the primary model returns 503 or 529.
  - Increased `max_tokens` from 512 to 1536 in `_stage1_plan` to avoid truncation on models generating reasoning tokens.
  - Increased `max_tokens` from 2048 to 4096 in `_stage2_file` and passed `active_model`.
  - Added `_parse_file_content` to extract code from JSON envelopes, markdown code fences, or plain text.
  - Updated `_parse_response` to strip `<think>.*?</think>` and `<reasoning>.*?</reasoning>` blocks.
  - Reduced `timeout_s` from 90.0 to 35.0 seconds in `_make_client`.
- **Reason:** Prevent generation freezes when `Nemotron-3_5-Lightning` experiences transient outages, prevent `finish_reason == "length"` token crashes on reasoning models, and cleanly parse LLM outputs.
- **Tests Performed:** Live model probe with `nvidia/nemotron-3-super-120b-a12b` produced valid AppSpec JSON in 10.2 seconds.

### 2. `src/sketchforge/ui/web_studio/studio.js`
- **Change:**
  - Added de-duplication guard: `let lastLoggedMessage = ""` in `generate()` poll timer.
  - Only appends to Agent Log when `job.progress !== lastLoggedMessage`.
- **Reason:** Eliminate the scrolling flood of identical `"Stage 1 — requesting AppSpec plan from Nemotron…"` log messages every 900 ms that created the illusion of an infinite hang.
- **Tests Performed:** Polling loop verified with static progress strings; duplicate logs suppressed.

### 3. `src/sketchforge/ui/web_studio.py`
- **Change:**
  - In `ProjectHandler._handle`: Attached `X-Studio-Token: backend.session_token` when proxying `/api/*` requests to the generated Flask backend child process.
  - In `StudioHandler._proxy_api`: Attached `X-Studio-Token: backend.session_token`.
- **Reason:** Resolve HTTP 401 Unauthorized errors on form submissions and data loading in preview iframes.
- **Tests Performed:** Form POST `/api/items` tested against running `BackendServer` with token; returns HTTP 201 Created and persists to SQLite.

### 4. `src/sketchforge/vision/preprocessing.py` & `contour_detection.py`
- **Change:**
  - Verified grid lattice micro-square suppression logic.
- **Reason:** Prevent periodic graph paper intersections from triggering 557 false-positive checkbox detections.
- **Tests Performed:** `benchmark_photographs.py` executed on `rough_mobile_ux.jpg`; predictions reduced from 627 to 39, false checkboxes eliminated.

---

## Known Regressions or Limitations
- **External Framework Requirements:** React + TypeScript (Vite) target requires Node.js/npm on the host machine to build and run.
- **Hosted Model Availability:** Nebius Token Factory endpoints experience occasional load spikes; candidate model fallback mitigates single-model outages.
