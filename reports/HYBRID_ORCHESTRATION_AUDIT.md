# Hybrid Orchestration Audit

**Date**: 2026-10-25  
**Auditor**: Principal AI Architect & Engineering Lead  
**Repository**: `c:\Users\akash\Downloads\sketchforge`  
**Status**: Architecture & State Machine Audit

---

## 1. Current State of Orchestration

In the SketchForge repository, orchestration is currently split across two distinct systems:

1. **Local Desktop Orchestrator (`src/sketchforge/orchestration/`)**:
   - `sketch_workflow.py`: Manages the 8-step pipeline: `load_image` $\to$ `analyze` $\to$ `build_design` $\to$ `validate` $\to$ `evaluate` $\to$ `inject` $\to$ `repair` $\to$ `save_outputs`.
   - `repair_workflow.py`: Executes the trial-and-evaluate auto-repair loop with a hard cap of 3 attempts per fault and stopping rules.
   - `step_registry.py`: Registers steps and manages context passing through `WorkflowState`.
   - `budget_manager.py` & `stopping_rules.py`: Protects against infinite loops, regression, and timeout.

2. **Web Studio Orchestrator (`src/sketchforge/ui/web_studio.py` & `generation/`)**:
   - Operates independently from `sketch_workflow.py`.
   - Uses an in-memory dictionary `_JOBS = {job_id: {"status": ..., "progress": ...}}`.
   - Dispatches work to background Python daemon threads (`self._generate`, `self._revise`).
   - Delegates directly to `studio_generator.py` and `ai_generator.py`.

---

## 2. Orchestration Gaps

| Requirement | Current Status | Finding |
|---|---|---|
| Unified State Machine | Partial | Desktop uses `WorkflowState`; Web Studio uses an untyped dictionary. Neither defines a formal lifecycle covering both local vision and remote LLM steps. |
| Job States | Limited | Web Studio supports only `running`, `complete`, `failed`. Lacks intermediate states: `analyzing_sketch`, `waiting_for_model`, `validating_spec`, `testing`, `repairing`. |
| Idempotency | Missing | Repeated clicks in Web Studio create multiple competing background threads with distinct UUIDs. |
| Process Cancellation | Desktop only | Desktop supports cooperative cancellation; Web Studio threads cannot be cancelled once started. |
| Error Granularity | Missing in Studio | When Stage 2 fails, Web Studio swallows the exception and reports only `Generating project from templates...`. |
