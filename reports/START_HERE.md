# SketchForge: Quick Start & Execution Guide

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`

---

## 1. Environment & Prerequisites

- **OS**: Windows 11 (AMD64)
- **Python**: 3.11+ (developed and verified on 3.11.9 / 3.13)
- **Hardware Acceleration**: NVIDIA GeForce RTX 4050 Laptop GPU (CUDA 12.4 supported)
- **Dependencies**: Installed in current environment (`pip list` confirms `opencv-python-headless`, `pyside6`, `openai`, `torch`, `flask`, `pytest`).

---

## 2. Startup Commands

### A. Run Headless End-to-End Demo (1.5 seconds, no credentials needed)
```powershell
python -m sketchforge demo
```
*What it does*: Loads a synthetic sketch (`login_page_synthetic.png`), runs OpenCV detection, builds a Design IR, injects a misalignment fault, measures the fault, repairs it with the auto-repair engine, verifies the repair, and writes renders/reports to `output/demo/`.

### B. Run Desktop Workbench GUI (Local-first desktop application)
```powershell
python -m sketchforge gui
```
*What it does*: Opens the native PySide6 desktop workbench with visual canvas, component tree, property inspector, undo/redo stack, and auto-repair panel.

### C. Run Web Studio IDE (Browser-based full-stack generator)
```powershell
python -m sketchforge studio --port 8000
```
*Access URL*: Open `http://127.0.0.1:8000/studio` in your browser.  
*What it does*: Serves the web-based studio with live prompt input, artboard preview, and preview proxies for generated SQLite/Flask backends.

### D. Verify Live Nebius Token Factory Connectivity
```powershell
python scripts/verify_nebius.py --enable --accept-egress
```
*What it does*: Sends a lightweight 1-token connectivity probe to `https://api.tokenfactory.nebius.com/v1/` using the `NEBIUS_API_KEY` in `.env`, enumerating available NVIDIA Nemotron models.

### E. Run Full Test Suite
```powershell
pytest -ra
```
*What it does*: Executes all 357 unit, integration, and end-to-end tests across the entire repository.
