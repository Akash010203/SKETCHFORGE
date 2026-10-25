# SketchForge

**SketchForge** is a local-first engineering workbench that transforms photos of hand-drawn sketches, wireframes, and screenshots into measured, editable designs and verified full-stack web applications.

It operates without hard cloud dependencies, running a sub-second OpenCV computer vision pipeline and local inference engine on your laptop, paired with an autonomous closed-loop visual verification and repair cycle.

---

## Architecture: Two Practical Phases

```
┌────────────────────────────────────────────────────────────────────────┐
│               PHASE 1: Handwritten Sketch → Design IR                  │
├────────────────────────────────────────────────────────────────────────┤
│  [Sketch Photo / Wireframe]                                            │
│        │                                                               │
│        ▼                                                               │
│  [OpenCV Vision Engine]                                                │
│    • Illumination flattening (shadow & glare removal)                  │
│    • Adaptive Otsu & Gaussian thresholding                             │
│    • Quadrilateral perspective correction & deskew                     │
│    • Contour hierarchy & bounding box proposals                        │
│        │                                                               │
│        ▼                                                               │
│  [Component Detection & Classification]                                │
│    • Multi-scale CNN feature pyramid + anchor classification           │
│    • Buttons, inputs, headings, cards, text, images, containers        │
│    • IoU & recall benchmarking against ground truth                    │
│        │                                                               │
│        ▼                                                               │
│  [Handwriting OCR & Layout Snapping]                                   │
│    • CRNN (CNN-BiLSTM-CTC) recognizer for handwritten labels           │
│    • Geometric containment hierarchy (parent-child trees)              │
│    • 8px grid snapping, margin normalization & alignment               │
│        │                                                               │
│        ▼                                                               │
│  [Canonical Design IR] ── Editable SVG / HTML / CSS / JSON            │
└────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│        PHASE 2: Design IR → Verified Full-Stack Project                │
├────────────────────────────────────────────────────────────────────────┤
│  [Hybrid Orchestrator + Nebius NVIDIA Provider]                        │
│    • NVIDIA Nemotron-3_5 & Llama via Nebius Token Factory              │
│    • Offline deterministic fallback templates (no network needed)      │
│    • RAG engine: Lexical + Vector search with Reciprocal Rank Fusion   │
│        │                                                               │
│        ▼                                                               │
│  [Full-Stack Project Generation]                                       │
│    • Frontend: React + TypeScript + Vite (or pure HTML5/CSS3)          │
│    • Backend: Python Flask + SQLite REST API (CRUD, auth, CORS)        │
│        │                                                               │
│        ▼                                                               │
│  [Autonomous Closed-Loop Visual Correction]                            │
│    1. Headless browser captures screenshot of rendered frontend        │
│    2. OpenCV scans rendered page and maps elements to Design IR        │
│    3. Measures IoU and position discrepancy                            │
│    4. Identifies concrete defects (missing button, displaced card)     │
│    5. Applies bounded code repair & re-verifies until layout matches   │
│        │                                                               │
│        ▼                                                               │
│  [Deliver Final Verified Full-Stack Project ZIP]                       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## The Design "Brain"

SketchForge enforces a coherent, human-centered design system across all generated code:

* **Typography Hierarchy**: Structured modular font scale from Display (32–40px) and Headings (20–28px) to Body (14–16px) and Captions (12px), paired with modern typography (Inter, Outfit, Roboto).
* **Color System**: Tailored semantic CSS tokens (`--background`, `--card`, `--primary`, `--border`, `--text`, `--muted`), guaranteed to meet WCAG AA contrast standards (>= 4.5:1).
* **Grid & Spacing**: Strict 8px spatial grid with automatic padding/margin normalization and responsive CSS flexbox/grid layouts across desktop, tablet, and mobile.
* **Micro-Interactions**: Smooth hover, active, and focus states on interactive elements (`transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1)`).

---

## Quickstart in 2 Minutes

### 1. Requirements
* Python 3.11+ (tested on Python 3.11 and 3.13)
* Dependencies: OpenCV, NumPy, Pydantic, Pillow, Flask

```bash
# Clone and setup environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Run the Autonomous Demo
```bash
python -m sketchforge demo
```
Runs the headless end-to-end pipeline in ~3 seconds: imports `login_page_synthetic.png`, analyzes it with OpenCV, builds the Design IR, injects a layout fault, detects it, auto-repairs it, and writes the before/after renders and reports to `output/demo/`.

### 3. Launch the Web Studio
```bash
python -m sketchforge studio
```
Open **`http://127.0.0.1:8000/studio`** in your browser.
* Drag and drop your hand-drawn sketch or screenshot.
* Describe what you want to build in the prompt bar.
* Watch the agent analyze the layout, build the Design IR, generate the full-stack project, and verify it visually.
* Download the complete verified project ZIP.

### 4. Launch the Desktop Workbench (Optional GUI)
```bash
python -m sketchforge gui
```
Open the PySide6 desktop workbench to interactively edit component boxes, inspect layers, tweak CSS variables, test auto-repair, and type natural-language design revisions.

---

## Dataset Ecosystem (200 GB Target)

SketchForge includes streaming dataset adapters and download scripts equipped with strict safety caps to prevent disk exhaustion:

| Dataset | Expected Size | Focus | Stream Command |
|---|---|---|---|
| **WebSight v0.2** | 20 GB cap | Webpage screenshot + HTML/Tailwind pairs | `python scripts/download_datasets.py --dataset websight-v02` |
| **WebCode2M** | 20 GB cap | Millions of real-world DOM trees, styles & bounding boxes | `python scripts/download_datasets.py --dataset webcode2m` |
| **Teklia IAM-line** | ~260 MB | Handwriting line recognition for sketch label OCR | `python scripts/download_datasets.py --dataset teklia-iam-line` |
| **Teklia IAM forms** | ~120 MB | Full page/form handwriting and layout detection | `python scripts/download_datasets.py --dataset teklia-iam` |
| **Sketch2Diagram** | ~130 MB | Hand-drawn diagrams, flowcharts, graphs, visual relationships | `python scripts/download_datasets.py --dataset sketch2diagram` |
| **SALT Sketch2Code** | ~80 MB | Direct hand-drawn sketches paired with clean HTML | `python scripts/download_datasets.py --dataset salt-sketch2code` |
| **CommitPackFT** | ~330 MB | Code repair, syntax patterns & edits (Python, TS, HTML) | `python scripts/download_datasets.py --dataset commitpackft` |
| **The Stack Dedup** | 20 GB cap | Curated web language source code | `python scripts/download_datasets.py --dataset the-stack-dedup` |

To download all small auxiliary datasets in under 2 minutes:
```bash
python scripts/download_datasets.py --small-all
```

---

## Verification & Self-Correction Engine

The visual verification loop in `src/sketchforge/verification/discrepancy_repair.py` ensures that generated code matches the sketch:

1. **Capture**: Playwright captures a headless screenshot of the running preview server.
2. **Scan**: OpenCV detects visible UI elements, calculates bounding boxes, and scales them to the design coordinate space.
3. **Compare**: Computes Intersection-over-Union (IoU) and centroid Euclidean distance against the source Design IR.
4. **Diagnose**: Formulates structured discrepancies (e.g. `MISSING_COMPONENT: btn_submit`, `POSITION_MISMATCH: inp_search (offset 42px)`).
5. **Repair**: Sends targeted diff requests to Nebius or local rule-based patchers, reapplies changes, and confirms the discrepancy score drops below threshold.

---

## Project Structure

```
sketchforge/
├── src/sketchforge/
│   ├── vision/            # OpenCV preprocessing, contour detection, OCR & perspective
│   ├── design_ir/         # Canonical Design IR schema, geometry, and serialization
│   ├── layout/            # 8px spatial grid alignment, hierarchy & grouping rules
│   ├── generation/        # Full-stack code generators: React+TS frontend & Flask backend
│   │   ├── frontend/      # Vite, React components, CSS modules & design tokens
│   │   └── backend/       # Python Flask REST API, SQLite schema & CRUD logic
│   ├── integrations/      # Nebius Token Factory (NVIDIA models) & local PyTorch runtime
│   ├── verification/      # Screenshot capture, OpenCV IoU discrepancy & repair loop
│   ├── retrieval/         # Hybrid RAG search (BM25 + Vector + Reciprocal Rank Fusion)
│   ├── datasets/          # Streaming adapters for WebSight, IAM, Sketch2Diagram, WebCode
│   ├── editor/            # Undo/redo stack, design commands, selection management
│   └── ui/                # Web Studio (Flask) & Desktop Workbench (PySide6)
├── scripts/               # Dataset download, preprocessing, and benchmark scripts
├── assets/sample_sketches/# Bundled test sketches (login, dashboard, mobile form, settings)
└── tests/                 # 370+ unit, integration, and end-to-end tests
```

---

## Running Tests

```bash
# Run all unit, integration, and end-to-end tests (headless, ~60 seconds):
python -m pytest -m "not ui" -q

# Run health check:
python -m pytest tests/test_health_check.py -v
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
