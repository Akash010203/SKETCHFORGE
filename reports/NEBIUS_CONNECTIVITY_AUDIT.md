# Nebius & NVIDIA Nemotron Connectivity Audit

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`  
**Status**: LIVE INFERENCE VERIFIED via Python backend

---

## 1. Provider Configuration & Authentication

- **Provider**: Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1/`)
- **Protocol**: OpenAI-compatible REST API (`openai.OpenAI(base_url=...)`)
- **SDK Version**: `openai` Python SDK (outbound only)
- **Credential Storage**: Reads `NEBIUS_API_KEY` from `.env` or host environment. Secrets are strictly kept out of version control and sanitized from client responses.
- **Privacy Policy**: SketchForge enforces `ConsentGate` and privacy checks before any outbound payload leaves the machine. By default in `config/providers.yaml`, `allow_images: false` and `include_user_text: false`.

---

## 2. Live Verification Probe Results

On 2026-10-25, we executed `python scripts/verify_nebius.py --enable --accept-egress` and verified direct connectivity to Nebius Token Factory:

```json
{
  "provider": "nebius",
  "status": "verified",
  "endpoint": "https://api.tokenfactory.nebius.com/v1/",
  "selected_model": "nvidia/Nemotron-3_5-Lightning",
  "completion": {
    "ok": true,
    "model": "nvidia/Nemotron-3_5-Lightning",
    "prompt_tokens": 23,
    "completion_tokens": 96,
    "latency_ms": 750.7
  },
  "models_endpoint": {
    "ok": true,
    "count": 30,
    "nvidia_models": [
      "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
      "nvidia/Nemotron-3-Ultra-550b-a55b",
      "nvidia/Nemotron-3.5-Super-VL",
      "nvidia/Nemotron-3_5-Lightning",
      "nvidia/nemotron-3-super-120b-a12b"
    ],
    "preferred_available": [
      "nvidia/Nemotron-3_5-Lightning",
      "nvidia/nemotron-3-super-120b-a12b"
    ]
  }
}
```

### Confirmed Findings:
1. `nvidia/Nemotron-3_5-Lightning`: Live and responsive (750.7 ms latency).
2. `nvidia/nemotron-3-super-120b-a12b`: Live and responsive.
3. `nvidia/Nemotron-3.5-Super-VL`: Listed in the catalog and reports `text+image->text` modality with a 1,048,576 token context window.

---

## 3. Live Stage 1 & Stage 2 Test Execution Evidence

We conducted direct Python backend tests to trace `ai_generator.py` through both stages:

### Stage 1 (AppSpec Plan): SUCCESS
- **Prompt**: `"A simple counter app"`
- **Model**: `nvidia/nemotron-3-super-120b-a12b`
- **Result**:
  ```text
  Stage 1 — requesting AppSpec plan from nvidia/nemotron-3-super-120b-a12b…
  Stage 1 complete (nvidia/nemotron-3-super-120b-a12b) — app: 'CounterApp', 1 page(s), 1 entity/entities.
  ```
  AppSpec plan was generated, returned valid JSON, and parsed into a dictionary successfully.

### Stage 2 (File Generation): PARTIAL FAILURE & DISCARD
When executing the 12-file manifest generation:
- `index.html`: OK
- `css/style.css`: OK
- `home.html`: OK
- `projects.html`: **FAILED**:
  `Stage 2 request for projects.html failed: the service returned an empty answer`
  (Skipping projects.html — model returned no content).
- `js/home.js`: OK
- `js/projects.js`: OK
- `backend/schema.sql`: OK
- `backend/models.py`: OK
- `backend/database.py`: OK
- `backend/logic.py`: OK
- `backend/api.py`: **FAILED**:
  `Stage 2 request for backend/api.py failed: the answer was cut off (max_tokens reached); it would not be valid JSON`
  (Skipping backend/api.py — model returned no content).
- `requirements.txt`: OK

### The Cascade Result:
```text
AI generation was incomplete (10/12 files); using the complete template generator instead.
Discarding incomplete AI project C:\Users\akash\Downloads\sketchforge\output\scratch_test\counterapp (2 file(s) missing).
FINAL RESULT: None
```

---

## 4. Why Stage 1 Appeared Stuck / Repeating

1. **Sequential Loop Timing**: In `ai_generator.py`:
   ```python
   for model in _CANDIDATE_MODELS:
       emit(f"Stage 1 — requesting AppSpec plan from {model}…")
       ...
       except Exception as exc:
           emit(f"Stage 1 with {model} unavailable ({exc}); trying candidate model…")
   ```
   If model 1 errors or times out (35 s timeout + retries = up to 70 s), the progress message is replaced immediately by candidate model 2. The browser UI polling every 900 ms captures multiple `Stage 1 — requesting AppSpec plan from...` entries.
2. **Missing Token or Rate Limiting**: If `NEBIUS_API_KEY` was missing in early runs, each model candidate failed immediately, flashing through candidate models and landing back at templates.
3. **Stage 2 Total Discard Loop**: Because 1 or 2 files in Stage 2 fail and cause the whole AI project to be deleted, users repeatedly submit new prompts, re-triggering Stage 1 over and over.
