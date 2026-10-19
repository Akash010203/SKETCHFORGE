# Implementation plan

Loop for every iteration: **inspect → design → implement → test → measure → diagnose → improve →
verify → document**. Smallest coherent change, then regression tests. Stop and reassess after three
failed attempts at the same failure. Never weaken a test to get a pass.

| Phase | Scope | State | Exit criterion |
|---|---|---|---|
| 0 | Environment, structure, decisions | done | environment recorded (`scripts/inspect_*`), ADRs written |
| 1 | Design IR + image pipeline + deterministic detection | done | tests + held-out benchmark |
| 2 | Editable renderer, editor, undo/redo, desktop workspace | done | UI smoke tests; edits update the IR |
| 3 | Evaluation + repair + closed loop | done | 337-cell matrix, 0 % regressed |
| 4 | NVIDIA/Nebius integration | **next** | official rules verified first; real remote task measured against the local baseline; local fallback |
| 5 | Dataset audit, manifests, pilot subset, held-out eval set | planned | licences recorded per source; small subset validated; disk budget checked |
| 6 | Compact detector trained from random init | planned | beats or honestly loses to the heuristic baseline on a held-out real+synthetic set |
| 7 | Natural-language design edits (validated against the IR) | planned | edit success rate measured; invalid edits rejected |
| 8 | React/TS frontend generation + verification | planned | generated app builds, lints, passes browser smoke test |
| 9 | Python backend generation (when the app needs one) | planned | schema, validation, migrations, tests pass |
| 10 | Restricted execution, screenshots, repair, rollback | planned | full loop on generated apps |
| 11 | Performance, packaging, hackathon materials | planned | reproducible demo from a clean checkout |

## Effort allocation

About 30 % of total engineering effort is reserved for Phase 4 (integration, evaluation, reliability,
demo). It is an effort target, not a lines-of-code target; no superficial wrappers.

## Constraints that shape the plan

* Hardware: 2 CPU cores, 7.8 GB RAM, no GPU, ~29 GB free disk. Phase 6 models must be tiny and
  CPU-trainable; datasets are sized against `scripts/inspect_storage.py` before any download.
* The application never grows an API server. Remote providers are outbound clients only.
* A claim (trained, licensed, passing, integrated) is made only after it is verified and recorded.
