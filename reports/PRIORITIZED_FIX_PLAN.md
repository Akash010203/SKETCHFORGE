# SKETCHFORGE — PRIORITIZED FIX & REPAIR PLAN

**Date:** October 24, 2026  
**Status:** Core fixes implemented; focused verification recorded below; live Studio browser and standalone executable verification remain open

---

## Priority 0 (Blockers — Critical User Impact)

| ID | Issue | Root Cause | Files Involved | Acceptance Criteria | Status |
|---|---|---|---|---|---|
| **FIX-01** | Duplicate Stage 1 log flooding | `studio.js` calls `addLog` on every 900ms poll tick unconditionally | `src/sketchforge/ui/web_studio/studio.js` | Only log when message text changes; display clean timeline | **Implemented; JS syntax checked; browser smoke pending** |
| **FIX-02** | Nebius 503/529 generation freeze | Hardcoded `Nemotron-3_5-Lightning` model + 90s timeout with no candidate fallback | `src/sketchforge/generation/ai_generator.py` | Fallback to `nemotron-3-super-120b-a12b`; 35s timeout; graceful template fallback | **Applied** |
| **FIX-03** | Reasoning token truncation | `max_tokens=512` in Stage 1 cuts off JSON when model outputs reasoning tokens | `src/sketchforge/generation/ai_generator.py` | Expand Stage 1 to 1536 tokens; strip `<think>` tags | **Applied** |
| **FIX-04** | Preview proxy drops `X-Studio-Token` (HTTP 401) | `ProjectHandler` & `StudioHandler._proxy_api` omit `X-Studio-Token` header | `src/sketchforge/ui/web_studio.py` | Proxy injects `X-Studio-Token: backend.session_token`; forms return 201/200 | **Implemented; `_proxy_api` header verified with in-process mock; full preview path pending** |

---

## Priority 1 (High — Major Usability & Robustness)

| ID | Issue | Root Cause | Files Involved | Acceptance Criteria | Status |
|---|---|---|---|---|---|
| **FIX-05** | Pre-generation sketch upload blocked | `/api/upload` required existing project slug | `src/sketchforge/ui/web_studio.py`, `studio.js` | Users can upload sketch before generating; runs OpenCV analysis | **Implemented; in-process route analyzed sample (15 detections); browser smoke pending** |
| **FIX-06** | No project ZIP export button | Studio lacked an archive download endpoint | `src/sketchforge/ui/web_studio.py`, `studio.js` | 1-click download of `<slug>.zip` containing all code | **Implemented; in-process route verified ZIP contents; browser smoke pending** |
| **FIX-07** | Grid-paper false checkboxes in CV | Regular grid lines detected as 557 checkbox contours | `src/sketchforge/vision/preprocessing.py`, `contour_detection.py` | Grid lattice suppression active; real photo benchmark n_pred ≤ 40 | **Verified Active** |

---

## Priority 2 (Medium — Feature Polish & Completeness)

| ID | Issue | Root Cause | Files Involved | Acceptance Criteria | Status |
|---|---|---|---|---|---|
| **FIX-08** | Template generator entity extraction | Always defaulted to `Submission` entity for custom prompts | `src/sketchforge/generation/studio_generator.py` | Heuristic keyword extractor infers custom nouns from prompt | **Implemented; custom and built-in prompts checked in-process** |
| **FIX-09** | Canvas tool placeholders | Several tool buttons showed "Coming Soon" alerts | `src/sketchforge/ui/web_studio/studio.js` | Wire up Theme toggle, Frame outline, and image insert | **Theme and frame implemented; image insertion already wired; browser smoke pending** |
| **FIX-10** | Missing Layout Model Checkpoint | `models/layout_model/` has PyTorch code but missing `.pt` file | `src/sketchforge/models/layout_model/` | Bundle weights or clearly document OpenCV contour fallback | **Documented Fallback** |

---

## Priority 3 (Low — Maintenance & Packaging)

| ID | Issue | Root Cause | Files Involved | Acceptance Criteria | Status |
|---|---|---|---|---|---|
| **FIX-11** | Windows standalone `.exe` build | PyInstaller spec exists in docs but unbundled | `scripts/package_application.py` | Automated build script produces portable Windows executable | **Build script exists; progress now streams; fresh build stalled during analysis and was interrupted; existing exe is stale** |
| **FIX-12** | AWS SAM Lambda live deploy | Cloud client implemented but requires manual SAM deploy | `deploy/aws/` | Documented 1-command deployment with verified endpoint | **Documented** |
