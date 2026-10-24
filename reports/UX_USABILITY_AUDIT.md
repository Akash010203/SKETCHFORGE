# SKETCHFORGE — UX & USABILITY AUDIT REPORT

**Date:** October 24, 2026  
**Evaluator Roles:** Independent User & Product Reviewers (Perspectives 21–25)  

---

## 1. Nontechnical First-Time User A (Upload Sketch to Working App)

### 1.1 Objective
Upload a hand-drawn website wireframe on paper and obtain a working web prototype without touching a terminal, editing code, or managing local servers.

### 1.2 Observed Findings
1. **Upload Gating Barrier:** Clicking the image upload icon (`＋`) in the prompt bar before an initial project had been generated produced the error:
   > *"Generate a project before adding an image."*
   A first-time user who arrived with a paper sketch in hand was blocked from uploading their sketch as the primary generation input.
2. **Infinite Log Illusion:** When prompt generation took more than 5 seconds, the Agent Log repeatedly prepended:
   > `"Stage 1 — requesting AppSpec plan from Nemotron…"`
   every 900 milliseconds. The rapid scrolling text created panic that the browser had frozen or the machine was locked in an infinite loop.
3. **HTTP 401 Form Failure:** Once an app was displayed in the preview, typing in a form and clicking submit resulted in:
   > `"Could not save: backend unavailable (HTTP 401)."`
   The user had no understanding of what "HTTP 401" meant or how to resolve it.

### 1.3 Recommended Corrections
- Enable pre-generation sketch upload directly on the empty canvas and in the prompt bar.
- Suppress duplicate log lines; display a step-by-step progress timeline with checkmarks.
- Forward authentication tokens transparently through the preview proxy.

---

## 2. Nontechnical First-Time User B (Error Recovery, Editing & Export)

### 2.1 Objective
Use the Studio independently, recover gracefully if AI services are down, make visual edits, and download the finished deliverable.

### 2.2 Observed Findings
1. **Lack of Download/Export Button:** The Studio topbar had buttons for Undo, Redo, Share, and Account, but no button to download the generated files as a `.zip` archive. Nontechnical users had no obvious way to obtain their files without browsing Windows Explorer into `output/projects/`.
2. **Coming Soon Tool Buttons:** 4 of the 7 canvas tool buttons (Frame, Draw, Pan, Theme) displayed "Coming Soon" notifications when clicked, frustrating attempts to modify the design.
3. **Double-Click Editing Usability:** Direct canvas text editing required double-clicking text inside the iframe, but there were no hover hints or cursor cues indicating that elements were editable.

### 2.3 Recommended Corrections
- Add an explicit "Export ZIP" action button to the top navigation bar.
- Provide clear visual hover outlines when edit mode is toggled.
- Provide a 1-click fallback notification when remote AI is offline: *"AI service unavailable; generated via high-speed template engine."*

---

## 3. Experienced AI Website-Builder User A (Prompting, Speed & Iteration)

### 3.1 Objective
Test prompt variations, rapid iterative revisions, responsive device previews, and generation latency.

### 3.2 Observed Findings
1. **Device Switcher Works Well:** The Desktop (1200px), Tablet (768px), and Mobile (375px) artboard switcher functioned smoothly, applying CSS classes and resizing the iframe cleanly.
2. **Popout Preview:** The popout button (`↗`) opens the preview in a dedicated browser tab at `http://127.0.0.1:<preview_port>/home.html`, which is excellent for full-screen testing.
3. **Slow Timeout on AI Failure:** When Nebius experienced high load, the system hung for 90–180 seconds before falling back. A prompt builder expects immediate feedback or a 15-second fallback.

---

## 4. Experienced AI Website-Builder User B (Code Editing & Component Control)

### 4.1 Objective
Inspect generated source code, review database schemas, verify API contracts, and customize components.

### 4.2 Observed Findings
1. **Clean Code Generation:** Generated projects contain clean, readable HTML5/CSS3 and Python Flask files with standard SQLite database helpers. No obfuscated code or heavy framework lock-in.
2. **Missing In-Studio Code Viewer:** While the file tree is readable on disk, the Web Studio lacked an embedded Monaco/CodeMirror code inspector to view or edit `backend/api.py` directly in the browser.
3. **Data Persistence Works:** Once the 401 token issue is resolved, data submitted through forms correctly persists to SQLite WAL databases and survives server reboots.

---

## 5. Product & Quality Lead Release Assessment

### 5.1 Release Blockers Identified
1. **Blocker 1 (P0):** Token proxy drop causing HTTP 401 on form submissions.
2. **Blocker 2 (P0):** UI duplicate log spam creating perceived hang on Stage 1.
3. **Blocker 3 (P0):** Hardcoded Nebius model causing generation failure during single-model outages.
4. **Blocker 4 (P1):** Inability to upload a sketch before generating a project.

### 5.2 Release Recommendation
**CONDITIONAL RELEASE READY:** With the 4 core fixes applied (token forwarding, log de-duplication, candidate model fallback, and sketch upload enablement), SketchForge provides a functional physical-AI to full-stack workflow.
Human usability testing with external users remains pending.
