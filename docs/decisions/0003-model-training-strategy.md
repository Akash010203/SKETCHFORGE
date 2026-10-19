# ADR 0003 — Heuristics first; train small models from scratch only against a measured baseline

**Status:** accepted (Phase 6 not started) · **Date:** 2026-10-17

**Decision.** Milestone 1 uses deterministic OpenCV heuristics with explicit, testable rules and
recorded confidence/ambiguity. A learned component detector is added in Phase 6 **only** as a
compact model initialised randomly (no pretrained weights, so the "trained from scratch" claim is
true), trained with fixed seeds and a train/validation/test split by source layout/template to avoid
leakage, and compared with the heuristic baseline on held-out real *and* synthetic sets reported
separately.

**Constraints that shape it.** Current machine: 2 CPU cores, 7.8 GB RAM, no GPU, PyTorch not
installed, ~14.7 GB planning budget for data. So: tiny convolutional detector, small images, bounded
batch sizes, CPU fallback, checkpoints + resume, early stopping on validation, a smoke test (batch
loads → forward → finite loss → backward → checkpoint round-trip → valid inference) before any full
run. No claim of success from training loss alone.

**Third-party models** (e.g. the NVIDIA/Nebius integration) are separate, isolated, labelled as not
trained by us, and never counted as "from scratch".

**Exit rule.** If the learned detector does not beat the heuristics on the held-out set, the
heuristics stay the default and the result is documented as such.
