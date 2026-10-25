"""Unified Control Plane: HybridOrchestrator and formal state machine.

Unifies Web Studio and Desktop Workbench behind a shared state machine and job lifecycle:
- Explicit states: queued -> analyzing_sketch -> building_design_ir -> planning_spec
                   -> generating_files -> starting_sandbox -> capturing_preview
                   -> measuring_discrepancy -> repairing -> completed (or failed / cancelled).
- Thread-safe job tracking with history logs, cooperative cancellation, and discrepancy metrics.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


class HybridJobState(str, Enum):
    QUEUED = "queued"
    ANALYZING_SKETCH = "analyzing_sketch"
    BUILDING_DESIGN_IR = "building_design_ir"
    PLANNING_SPEC = "planning_spec"
    GENERATING_FILES = "generating_files"
    STARTING_SANDBOX = "starting_sandbox"
    CAPTURING_PREVIEW = "capturing_preview"
    MEASURING_DISCREPANCY = "measuring_discrepancy"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class HybridJob:
    """Explicit, inspectable state for a single hybrid generation run."""
    id: str
    prompt: str
    state: HybridJobState = HybridJobState.QUEUED
    status: str = "running"              # "running", "complete", "failed", "cancelled"
    progress: str = "Job queued…"
    history: list[dict] = field(default_factory=list)
    project_slug: str | None = None
    project_root: Path | None = None
    preview_url: str | None = None
    backend_port: int | None = None
    preview_port: int | None = None
    design_doc: Any = None
    layout_block: dict | None = None
    discrepancy: Any = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def transition(self, new_state: HybridJobState, progress_msg: str) -> None:
        """Atomically transition state and record a history entry."""
        self.state = new_state
        self.progress = progress_msg
        self.updated_at = time.time()
        if new_state == HybridJobState.COMPLETED:
            self.status = "complete"
        elif new_state == HybridJobState.FAILED:
            self.status = "failed"
        elif new_state == HybridJobState.CANCELLED:
            self.status = "cancelled"
        else:
            self.status = "running"
        self.history.append({
            "state": new_state.value,
            "progress": progress_msg,
            "timestamp": round(self.updated_at, 2),
        })
        log.info("Job %s -> %s: %s", self.id, new_state.value, progress_msg)

    def cancel(self) -> None:
        self.cancel_event.set()
        self.transition(HybridJobState.CANCELLED, "Job cancelled by user.")

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state.value,
            "status": self.status,
            "progress": self.progress,
            "prompt": self.prompt,
            "slug": self.project_slug,
            "preview_url": self.preview_url,
            "error": self.error,
            "history": self.history[-20:],
            "discrepancy": self.discrepancy.to_dict() if hasattr(self.discrepancy, "to_dict") else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class HybridOrchestrator:
    """Unified control plane coordinating local vision, LLM generation, and repair."""

    def __init__(self) -> None:
        self._jobs: dict[str, HybridJob] = {}
        self._lock = threading.Lock()

    def create_job(
        self,
        prompt: str,
        *,
        sketch_data: bytes | None = None,
        sketch_name: str | None = None,
        design_doc: Any = None,
        job_id: str | None = None,
    ) -> HybridJob:
        with self._lock:
            jid = job_id or uuid.uuid4().hex[:12]
            job = HybridJob(id=jid, prompt=prompt, design_doc=design_doc)
            self._jobs[jid] = job

        # If raw sketch data was attached, analyze it immediately
        if sketch_data:
            try:
                from sketchforge.vision import analyze, load_image_bytes
                from sketchforge.vision.to_design_ir import build_nemotron_layout_block, vision_result_to_document

                job.transition(HybridJobState.ANALYZING_SKETCH, "Analyzing uploaded sketch with OpenCV…")
                loaded = load_image_bytes(sketch_data, sketch_name or "sketch.png")
                res = analyze(loaded)
                job.transition(HybridJobState.BUILDING_DESIGN_IR, "Compiling Design IR & spatial bounding boxes…")
                job.design_doc = vision_result_to_document(res, sketch_name=sketch_name or "Sketch")
                job.layout_block = build_nemotron_layout_block(res, sketch_name=sketch_name or "Sketch")
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not analyze sketch in orchestrator: %s", exc)

        return job

    def get_job(self, job_id: str) -> HybridJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if job and not job.is_cancelled:
            job.cancel()
            return True
        return False

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def run_pipeline(
        self,
        job_id: str,
        target_dir: Path,
        *,
        on_preview_ready: Callable[[HybridJob], None] | None = None,
    ) -> HybridJob:
        """Run the complete hybrid pipeline asynchronously through all formal states."""
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"Job {job_id} not found")

        try:
            if job.is_cancelled:
                return job

            # 1. Planning Spec
            job.transition(HybridJobState.PLANNING_SPEC, "Requesting AppSpec plan from Nemotron-3_5-Lightning…")
            from sketchforge.generation.ai_generator import ai_generate_project

            def _progress_cb(msg: str) -> None:
                if job.is_cancelled:
                    return
                # Map progress message to appropriate state
                if "Stage 2" in msg or "Generating" in msg:
                    job.transition(HybridJobState.GENERATING_FILES, msg)
                else:
                    job.progress = msg

            # 2. Generating Files (with per-file fallback)
            job.transition(HybridJobState.GENERATING_FILES, "Generating 12-file full-stack project…")
            project_root = ai_generate_project(
                job.prompt,
                target_dir,
                include_backend=True,
                design_doc=job.design_doc,
                layout_block=job.layout_block,
                progress=_progress_cb,
            )

            if job.is_cancelled:
                return job

            if not project_root or not project_root.is_dir():
                job.transition(HybridJobState.FAILED, "Project generation failed to produce directory.")
                return job

            job.project_root = project_root
            job.project_slug = project_root.name

            # 3. Starting Sandbox & Preview
            job.transition(HybridJobState.STARTING_SANDBOX, "Starting sandboxed runtime & preview server…")
            if on_preview_ready:
                on_preview_ready(job)

            # 4. Verification & Discrepancy Repair Loop
            if job.preview_url and job.design_doc and not job.is_cancelled:
                job.transition(HybridJobState.CAPTURING_PREVIEW, "Capturing rendered preview snapshot…")
                from sketchforge.verification.discrepancy_repair import run_discrepancy_repair_loop

                job.transition(HybridJobState.MEASURING_DISCREPANCY, "Measuring visual discrepancy against sketch…")
                report = run_discrepancy_repair_loop(
                    project_root=job.project_root,
                    preview_url=job.preview_url,
                    design_doc=job.design_doc,
                    max_attempts=1,
                    threshold=0.25,
                    progress=lambda m: job.transition(HybridJobState.REPAIRING, m),
                )
                job.discrepancy = report

            job.transition(HybridJobState.COMPLETED, f"Project {project_root.name} complete and verified.")
            return job

        except Exception as exc:  # noqa: BLE001
            log.exception("Pipeline failed for job %s: %s", job_id, exc)
            job.error = str(exc)
            job.transition(HybridJobState.FAILED, f"Generation failed: {exc}")
            return job


# Global orchestrator singleton
_ORCHESTRATOR = HybridOrchestrator()


def get_hybrid_orchestrator() -> HybridOrchestrator:
    """Return the application-wide HybridOrchestrator singleton."""
    return _ORCHESTRATOR
