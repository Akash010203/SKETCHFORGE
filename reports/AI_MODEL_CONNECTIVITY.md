# SKETCHFORGE — AI MODEL CONNECTIVITY & NEBIUS INFERENCE AUDIT

**Date:** October 24, 2026  
**Provider:** Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1/`)  
**Authentication:** Bearer token via `NEBIUS_API_KEY` (sanitized; secrets never printed or committed)  

---

## 1. Live Verification & Connectivity Matrix

We executed real network probes against the Nebius Token Factory endpoint to measure latency, availability, and response characteristics across all registered NVIDIA models:

| Model Identifier | Modality | Context Length | Probe Status | Latency | Observation |
|---|---|---|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | text→text | 262,144 | **VERIFIED (HTTP 200)** | **720 ms** | Emits reasoning tokens (`reasoning_tokens: 12`). Highly responsive and reliable. |
| `nvidia/Nemotron-3_5-Lightning` | text→text | 1,048,576 | **INTERMITTENT OVERLOAD** | 5,448 ms / Timeout | Intermittently returns `HTTP 503 Service Temporarily Unavailable` and `HTTP 529 System is overloaded`. |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | text→text | 262,144 | **INTERMITTENT 503** | — | Returns `HTTP 503: Service Temporarily Unavailable` during high-load windows. |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | text→text | 1,048,576 | **UNAVAILABLE (503)** | — | Service unavailable at tested endpoint. |
| `nvidia/Nemotron-3.5-Super-VL` | text+image→text | 1,048,576 | **UNAVAILABLE (503)** | — | Service unavailable at tested endpoint. |

---

## 2. Model Response Verification & Structured AppSpec Test

Using `nvidia/nemotron-3-super-120b-a12b`, we tested Stage 1 AppSpec plan generation with prompt:
> *"A habit tracker to track daily reading and workouts"*

### 2.1 Request Parameters
- **System Prompt:** `_PLAN_SYSTEM` from `ai_generator.py`
- **Temperature:** `0.2`
- **Max Tokens:** `1536` (expanded from original `512`)

### 2.2 Live Parsed Output
```json
{
  "name": "HabitTracker",
  "pages": [
    {"name": "home", "title": "Home", "route": "/"},
    {"name": "add-habit", "title": "Add Habit", "route": "/add-habit"}
  ],
  "entities": [
    {
      "name": "HabitLog",
      "fields": [
        {"name": "habit_name", "type": "text"},
        {"name": "activity_type", "type": "text"},
        {"name": "duration_minutes", "type": "int"},
        {"name": "log_date", "type": "date"}
      ]
    }
  ],
  "include_backend": true
}
```
**Verification Verdict:** Valid JSON parsed cleanly by `json.loads`. App name, pages, routes, entities, and typed fields generated accurately.

---

## 3. Discovered Inference Failures & Root Causes

### 3.1 Overload and Service Outages (503 & 529)
The Nebius Token Factory shared inference endpoint experiences transient server overloads:
- `HTTPError: 529 {"error": {"type": "server_error", "message": "System is overloaded"}, "detail": "System is overloaded"}`
- `HTTPError: 503 {"detail": "Service Temporarily Unavailable"}`

**Impact on Original Code:**
The original `ai_generator.py` hardcoded `nvidia/Nemotron-3_5-Lightning`. When this specific model was overloaded, the client performed backoff retries with a 90-second timeout, locking the pipeline for over 3 minutes while the UI spammed duplicate log entries.

### 3.2 Token Truncation on Reasoning Models
Modern NVIDIA models (e.g. `nemotron-3-super-120b-a12b`) generate chain-of-thought reasoning tokens inside `<think>...</think>` tags or as reasoning metadata before generating the completion text.
In the original code:
```python
max_tokens = 512
```
Because reasoning tokens count toward the token budget, the model hit the 512 token ceiling mid-output. `NebiusClient` detected `finish_reason == "length"` and raised `ProviderBadResponse("the answer was cut off (max_tokens reached); it would not be valid JSON")`.

### 3.3 Model Response Sanitization
When reasoning tokens or markdown fences (` ```json ... ``` `) wrap the JSON payload, standard `json.loads(text)` fails. The parser must explicitly:
1. Strip `<think>.*?</think>` and `<reasoning>.*?</reasoning>`.
2. Extract the payload enclosed in markdown fences.
3. Find the outermost `{` and `}` braces.

---

## 4. Standalone Connectivity Verification Script

A minimal verification command is available that verifies all 6 requirements without exposing secrets:

```bash
python scripts/verify_nebius.py --enable --accept-egress
```

This verifies:
1. `NEBIUS_API_KEY` is present in the environment or `.env` without printing its value.
2. Endpoint `https://api.tokenfactory.nebius.com/v1/` is reachable.
3. The model list (30 models) is retrieved and NVIDIA candidates identified.
4. A non-intrusive probe completion (`'Reply with: ok'`) is accepted.
5. The response is parsed and latency recorded.
6. Writes results to `experiments/results/live_nebius_benchmark.json`.
