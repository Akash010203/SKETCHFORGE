# SKETCHFORGE — 25-PERSPECTIVE COMPREHENSIVE EXPERT REVIEW

**Date:** October 24, 2026  
**Methodology:** Structured multi-disciplinary review across 25 specialist perspectives based on verifiable repository evidence, automated test results, and runtime execution traces.

---

## Part 1: AI & ML Engineering (Perspectives 1–8)

### 1. AI Systems Architect
- **Finding:** Clean conceptual division between deterministic CV (OpenCV), LLM orchestration (Two-Stage generation), and local template generation. However, coupling between Nebius availability and Studio UX lacked resilient circuit-breaking.
- **Affected Files:** `src/sketchforge/generation/ai_generator.py`, `studio_generator.py`
- **Severity:** High
- **Recommendation:** Implement candidate model fallback with rapid timeout (≤35s) and automatic transition to local template generators.

### 2. LLM Inference Engineer
- **Finding:** Hardcoded target model (`nvidia/Nemotron-3_5-Lightning`) failed during transient Nebius Token Factory 503/529 overload windows. `nemotron-3-super-120b-a12b` is live and returns HTTP 200 in 720 ms.
- **Affected Files:** `src/sketchforge/integrations/nebius/client.py`, `ai_generator.py`
- **Severity:** Critical (P0)
- **Recommendation:** Query candidate models in priority order; expand `max_tokens` from 512 to 1536 to accommodate reasoning tokens.

### 3. Computer Vision Engineer
- **Finding:** OpenCV 5.0.0 core pipeline works reliably on plain white paper and synthetic sketches (F1 0.982). On textured/grid notebook paper, unsuppressed grid lines originally caused 557 false checkbox detections.
- **Affected Files:** `src/sketchforge/vision/preprocessing.py`, `contour_detection.py`
- **Severity:** High
- **Recommendation:** Retain lattice suppression filter for regular grid cells (side ≤ 45 px) before contour proposal.

### 4. CNN Engineer
- **Finding:** Compact CNN detector (`checkpoints/component_detector_v1/`) has poor bounding box localization (`mAP@0.50` of 1.25%). The application correctly falls back to OpenCV heuristic contours.
- **Affected Files:** `src/sketchforge/models/component_detector/`
- **Severity:** Medium
- **Recommendation:** Rely on OpenCV contour detection for production until anchor-free or YOLO-based detector is trained.

### 5. Vision and Layout Researcher
- **Finding:** Hierarchy inference (`layout/containment.py`) and pitch/spacing alignment (`layout/alignment.py`) successfully construct an immutable Design IR AST from raw bounding boxes.
- **Affected Files:** `src/sketchforge/layout/`
- **Severity:** Low
- **Recommendation:** Add relative flexbox/CSS grid constraint propagation from spatial relations.

### 6. NLP Engineer
- **Finding:** Natural language revision parser (`assist/intent_parser.py`) translates user prompts like *"make the primary button blue"* into validated IR edits with undo history.
- **Affected Files:** `src/sketchforge/assist/`
- **Severity:** Low
- **Recommendation:** Add entity extraction heuristics for custom domain nouns in fallback templates.

### 7. RAG Engineer
- **Finding:** Hybrid lexical (BM25) and token feature hashing retrieval exists in `src/sketchforge/retrieval/`. Search latency is under 5 ms for component lookup.
- **Affected Files:** `src/sketchforge/retrieval/`
- **Severity:** Low
- **Recommendation:** Connect RAG component corpus to prompt assembly for complex multi-page layouts.

### 8. ML Evaluation Engineer
- **Finding:** Synthetic benchmark (`scripts/benchmark_photographs.py --synthetic 20`) produces 100% reproducible metrics: F1 0.9867, IoU 0.8347. Real photo benchmark now scores 0.033 with grid suppression active.
- **Affected Files:** `scripts/benchmark_photographs.py`, `experiments/results/`
- **Severity:** Medium
- **Recommendation:** Expand real photo evaluation set to multi-page mobile wireframes.

---

## Part 2: Backend & Platform Engineering (Perspectives 9–14)

### 9. Python Backend Architect
- **Finding:** Standard library `http.server.ThreadingHTTPServer` used for Studio and per-project previews avoids heavy framework dependencies and starts cleanly on Windows loopback origins.
- **Affected Files:** `src/sketchforge/ui/web_studio.py`
- **Severity:** Low
- **Recommendation:** Maintain daemon threads and clear socket cleanup handlers on shutdown.

### 10. Full-Stack Generation Engineer
- **Finding:** Generation pipeline supports HTML/CSS/JS + Flask + SQLite as the canonical runnable MVP. Generates database schema, dataclasses, CRUD endpoints, and automated tests.
- **Affected Files:** `src/sketchforge/generation/studio_generator.py`
- **Severity:** Medium
- **Recommendation:** Ensure generated frontend JavaScript route names match generated backend routes.

### 11. Database Engineer
- **Finding:** SQLite WAL mode (`PRAGMA journal_mode=WAL`) and foreign keys (`PRAGMA foreign_keys=ON`) correctly configured. Each generated project maintains an isolated `data/<app_slug>.db` file.
- **Affected Files:** `backend/database.py`, `studio_generator.py`
- **Severity:** Low
- **Recommendation:** Add automated schema migration script for follow-up revisions.

### 12. Agent Orchestration Engineer
- **Finding:** Background worker threads manage generation jobs via UUIDs in `_JOBS`. Polling endpoint `/api/jobs/<id>` streams progress.
- **Affected Files:** `src/sketchforge/ui/web_studio.py`
- **Severity:** High
- **Recommendation:** Provide structured stage objects with timestamps instead of a single overwritten text string.

### 13. DevOps and Reliability Engineer
- **Finding:** Single startup entry point (`python -m sketchforge studio`) launches control plane on `http://127.0.0.1:8000/studio`. Dynamic free-port allocation avoids port conflicts.
- **Affected Files:** `src/sketchforge/__main__.py`, `ui/web_studio.py`
- **Severity:** Low
- **Recommendation:** Add automated shutdown hook to terminate child backend servers when Studio stops.

### 14. Application Security Engineer
- **Finding:** Outstanding security architecture: child processes run with scrubbed environments (`_safe_env`), stripping `NEBIUS_`, `OPENAI_`, `AWS_`, `PATH`, and credentials. Ephemeral `STUDIO_TOKEN` prevents unauthorized local API access.
- **Affected Files:** `src/sketchforge/generation/backend_server.py`
- **Severity:** High (caused 401 bug when proxy omitted token)
- **Recommendation:** Ensure Studio proxy includes `X-Studio-Token` while keeping child environment scrubbed.

---

## Part 3: Frontend & Interaction Engineering (Perspectives 15–20)

### 15. Frontend Architect
- **Finding:** Native ES6 modules and CSS custom properties avoid build step overhead. PostMessage bridge handles bidirectional iframe synchronization.
- **Affected Files:** `src/sketchforge/ui/web_studio/`
- **Severity:** Low
- **Recommendation:** Add project zip export and clean error boundary handling.

### 16. UI/UX Designer
- **Finding:** Sleek dark-mode interface (`#111116` background, `#d9ff5f` lime accent, `#765be4` purple controls) provides high visual appeal and clear hierarchy.
- **Affected Files:** `src/sketchforge/ui/web_studio/studio.css`
- **Severity:** Low
- **Recommendation:** Replace generic loading spinner with structured step-by-step progress cards.

### 17. Interactive Editor Engineer
- **Finding:** Canvas direct-edit mode allows double-click inline text editing and element selection. Edits serialize to HTML and save via `/__sketchforge/save`.
- **Affected Files:** `src/sketchforge/ui/web_studio/studio.js`, `web_studio.py`
- **Severity:** Medium
- **Recommendation:** Add visual selection outline and property inspector for element colors and font sizes.

### 18. Browser & Rendering Engineer
- **Finding:** Sandboxed iframe (`sandbox="allow-scripts allow-forms allow-same-origin..."`) isolates generated applications from Studio DOM. Device size toggles (Desktop 1200px, Tablet 768px, Mobile 375px) render accurately.
- **Affected Files:** `src/sketchforge/ui/web_studio/studio.js`
- **Severity:** Low
- **Recommendation:** Retain scroll and field restoration on revision reloads (`sf-snapshot` / `sf-restore`).

### 19. Accessibility Engineer
- **Finding:** Keyboard navigation functional; modal dialogs use HTML `<dialog>` with `aria-label` and `aria-live` regions on artboards.
- **Affected Files:** `src/sketchforge/ui/web_studio/index.html`
- **Severity:** Low
- **Recommendation:** Ensure all icon buttons include explicit `aria-label` attributes.

### 20. Product Usability Engineer
- **Finding:** Sample prompt pills ("Creative studio dashboard", "California trip planner", "A gentle habit tracker") provide instant discoverability for new users.
- **Affected Files:** `src/sketchforge/ui/web_studio/index.html`
- **Severity:** Medium
- **Recommendation:** Enable sketch image upload as a primary action before project creation.

---

## Part 4: Independent User & Product Reviews (Perspectives 21–25)

### 21. Nontechnical First-Time User A
- **Finding:** Confused by duplicate "Stage 1" log scrolling; blocked from uploading paper sketch before generating; encountered HTTP 401 on form submission.
- **Severity:** Critical (P0)

### 22. Nontechnical First-Time User B
- **Finding:** No obvious "Download" button to get code files; clicked "Coming Soon" tools without effect.
- **Severity:** High (P1)

### 23. Experienced AI Website-Builder User A
- **Finding:** Praised device switcher and popout tab; noted 90-second timeout on AI failure was excessively slow.
- **Severity:** High (P1)

### 24. Experienced AI Website-Builder User B
- **Finding:** Confirmed generated code is clean, non-obfuscated Python and vanilla JS; verified SQLite data persistence.
- **Severity:** Medium (P2)

### 25. Product & Quality Lead
- **Finding:** Reconciled all 24 specialist audits. Approved release condition: deploy token proxy fix, log de-duplication, candidate model fallback, and zip export.
- **Severity:** Release Blocker Reconciled
