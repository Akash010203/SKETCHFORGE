# SKETCHFORGE — QUICK START & OPERATOR GUIDE

**Target System:** Windows 10/11 | Python 3.10+  
**Access URL:** `http://127.0.0.1:8000/studio`  

---

## 1. Environment Setup

### 1.1 Requirements
- Python 3.10, 3.11, or 3.12
- Optional: Virtual environment activated

### 1.2 Configuration (No Secrets in Code)
Copy `.env.example` to `.env` in the repository root:

```powershell
Copy-Item .env.example .env
```

To enable live Nebius AI model inference, edit `.env` and set:
```ini
NEBIUS_API_KEY="your-nebius-token-factory-key"
```
*(Note: If `NEBIUS_API_KEY` is absent or the service is offline, SketchForge operates in local mode using the built-in full-stack template engine).*

---

## 2. Launching SketchForge Studio (Single Startup Command)

To launch the unified Studio control plane:

```powershell
python -m sketchforge studio
```

Output:
```
SketchForge Studio is available at http://127.0.0.1:8000/studio
```

Open your browser to:
👉 **[http://127.0.0.1:8000/studio](http://127.0.0.1:8000/studio)**

---

## 3. How to Generate Your First Application

1. **Option A — Quick Idea Pills:**
   Click one of the prompt suggestions on the canvas (e.g., *"A gentle habit tracker with weekly progress and gentle reminders"*).
2. **Option B — Custom Text Prompt:**
   Type your brief into the bottom prompt bar (e.g., *"A modern booking app for a neighborhood yoga studio"*) and click the **↑** arrow (or press Enter).
3. **Option C — Sketch to App:**
   Click the **＋** button in the prompt bar to attach a sketch image (PNG or JPG). SketchForge will extract layout components and synthesize a matching full-stack app.

---

## 4. Other Available Entry Points

| Command | Purpose |
|---|---|
| `python -m sketchforge studio` | Starts the browser Web Studio (Port 8000) |
| `python -m sketchforge gui` | Launches the native PySide6 Desktop Workbench |
| `python -m sketchforge demo` | Headless 8-step image→design→repair demo |
| `python -m sketchforge info` | Prints installed versions (OpenCV, PySide6, Python) |
| `python scripts/verify_nebius.py --enable --accept-egress` | Runs the live Nebius API connectivity probe |
| `pytest` | Executes the complete 357-test automated verification suite |

---

## 5. Troubleshooting & Diagnostics

- **Agent Log Toggle:** Click **🚀 Agent log** in the left sidebar to view live progress messages.
- **Preview Frame Status:** Look at the top bar of the canvas. If the status says *"Ready"*, the postMessage bridge and backend are operational.
- **Inspect Generated Code:** Generated code is written to `output/projects/<slug>/`. You can open `backend/api.py`, `home.html`, and `data/<slug>.db` directly in your code editor.
