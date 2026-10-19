# NVIDIA / Nebius integration

**Status: rules verified (2026-10-18) · client IMPLEMENTATION in progress · live calls NOT yet verified.**
Nothing in this file claims a remote call has worked. See "Verification status" at the bottom.

## 1. Official requirements (verified from the official pages, 2026-10-18)

Sources: Devpost hackathon page <https://nebiusglobalaihackathon.devpost.com/> and its rules page
<https://nebiusglobalaihackathon.devpost.com/rules>; Token Factory docs
<https://docs.tokenfactory.nebius.com/> (`llms.txt` index, API introduction, vision, legal quick guide,
August-2026 deprecation notice).

| Item | Requirement as published |
|---|---|
| Hackathon | Nebius x NVIDIA Global AI Hackathon (Devpost). Tracks: Coding and Agentic Engineering · Best Apps and Agents · Personal AI · Physical AI |
| **Deadline** | **Friday 30 Oct 2026, 10:00 am Pacific Time** (= 22:30 IST the same day) |
| Platform | "a working software application that **runs on either Nebius Token Factory or Nebius AI Cloud**" and "**uses at least one NVIDIA open source model**" (Nemotron or other NVIDIA open models) |
| What "runs on" means | the project "makes a **runtime call to the Token Factory inference API**", or "is deployed/run using Nebius AI Cloud compute" (Serverless Jobs / Endpoints / DevPods) |
| Repository | public, with an open-source license file visible at the top of the repo (e.g. **Apache 2.0, MIT, MPL 2.0**), all source + README with setup instructions; README must say how NVIDIA models are used, where Token Factory helped, other Nebius tools used |
| Demo | URL to "a working demo, hosted application, or **test build**" (not needed for Physical AI); public YouTube video **< 3 min** showing the project working on the device it was built for; available free of charge and without restriction until judging ends |
| Other | project description; feedback on Nebius Token Factory / AI Cloud / NVIDIA tools; original work solely owned by the entrant; if it pre-dates the submission period, a written explanation of what was significantly updated; must not derive from work with financial/preferential support from the sponsor |
| Judging (equal weight) | Technological Implementation · Design (a complete coherent product, not a proof of concept) · Potential Impact · Quality of the Idea |
| Not stated on the pages read | any rule on AI coding tools (the full Official Rules should be read by the entrant before submitting) |

**Token Factory facts** (docs): OpenAI-compatible API, base URL `https://api.tokenfactory.nebius.com/v1/`,
`Authorization: Bearer <key>`, key conventionally in `NEBIUS_API_KEY`, chat completions at
`POST /v1/chat/completions`, models at `GET /v1/models` (`?verbose=true` adds modality), structured
output ("JSON") and function calling documented, image input documented as OpenAI-style
`image_url` content parts. **Data handling** (Legal Quick Guide): without Zero Data Retention (ZDR)
"we keep your inputs and outputs to speed up inference" (stored in Finland/EU; may be used for
speculative decoding); content is **not used to train** models in either mode; ZDR is an
organisation-level setting; public endpoints' processing location is decided dynamically.

**NVIDIA models on Token Factory.** The *August 2026 deprecation notice* removed
`nvidia/Nemotron-3-Nano-Omni`, `nvidia/Llama-3_1-Nemotron-Ultra-253B-v1` and `nvidia/Cosmos3-Super-Reasoner`
from serverless on 31 Aug 2026 and names these NVIDIA replacements: **`nvidia/Nemotron-3_5-Lightning`**
and **`nvidia/nemotron-3-super-120b-a12b`**. Whether those two accept image input is **not stated** in
the pages read, and the live model list needs an API key. The integration is therefore
*capability-driven* (see §3) and the exact IDs must be confirmed by `scripts/verify_nebius.py`.

## 2. What this means for SketchForge

* The no-application-API rule stands: SketchForge only ever acts as an **outbound client**. A
  runtime call to the Token Factory inference API satisfies "runs on Token Factory"; no server of ours
  is created and no cloud backend of ours exists.
* **Privacy by construction.** The default remote task sends a *compact structured summary* of the
  design (ids, types, rounded boxes, tree) plus the user's instruction — **never the sketch image**, and
  never the text inside components unless the user opts in (`include_user_text`).
* **Off by default; explicit consent.** The client refuses to send unless the provider is enabled in
  configuration *and* the user acknowledged the egress notice for this session. The notice states what
  is sent, where, and Nebius's retention behaviour (ZDR off ⇒ inputs/outputs retained).
* **The model proposes, local code disposes.** Model output is parsed into a typed edit plan,
  validated against the Design IR rules, applied as an ordinary undoable command, then checked by the
  same evaluator and bounded repair loop as everything else. A malformed or unsafe answer is rejected,
  never "fixed up" silently.
* **Demo/testing requirement.** The hackathon wants a "working demo … or test build" URL. SketchForge
  is a desktop application; a downloadable test build (GitHub release) is the architecture-compatible
  route. Whether the organisers accept that is for the entrant to confirm with them. Hosting our own
  demo server is excluded by the project rules.

## 3. Design (this phase)

```
assist/  (edit plans, local rule parser, model planner, verified apply)
   │ typed objects only
integrations/provider_interface.py   ModelProvider · CompletionRequest/Result · ProviderError family
   │
integrations/nebius/   configuration · request_policy · client (OpenAI SDK) · model_registry · health_check
integrations/nvidia/   model_configuration (eligible model ids + capability notes)
```

Provider capabilities are discovered, not assumed (`model_registry`): text-only vs image input,
JSON-mode availability. Timeouts, bounded retries (429/5xx/timeouts only, capped backoff), response
validation and per-request latency/usage tracking are implemented in `client.py`; the code that
uses a provider never sees Nebius's response format.

## 4. Benchmark (spec §10): three arms

1. **Local deterministic baseline** — rule-based parser for natural-language edits.
2. **Local + model assistance** — Nemotron on Token Factory translates the instruction into an edit plan.
3. **Integrated** — arm 2 + local validation, evaluator check and bounded repair.

Task set: `tests/evaluation/edit_tasks.json` (instruction → machine-checkable expectation).
Metrics: edit success, invalid-plan rate, new layout issues introduced, repair success, latency,
tokens. Run: `python scripts/run_visual_benchmark.py --provider nebius` (needs a key and network).
A neutral or negative result is reported as such.

## 5. Verification status

| Claim | Status | Evidence |
|---|---|---|
| Official rules read and recorded | VERIFIED | this file, §1 |
| Client speaks the documented protocol | pending | unit tests with an in-process fake transport |
| A real call to Token Factory succeeds | **NOT VERIFIED** — sandbox proxy blocks `api.tokenfactory.nebius.com` (HTTP 403 on CONNECT) and no key is configured | run `scripts/verify_nebius.py` on a networked machine with `NEBIUS_API_KEY` |
| Model IDs exist and their capabilities | **NOT VERIFIED** | same script lists `/v1/models?verbose=true` |
| Benchmark improvement from the model | **NOT MEASURED** | needs the live run; fake-provider runs only test the harness |
