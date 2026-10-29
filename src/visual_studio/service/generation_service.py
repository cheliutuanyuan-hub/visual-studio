"""Generation service: the application core that wires the hexagon together.

This is the only place that knows about all the collaborators (scheduler,
planner, providers, quality checker, event bus, persistence). Adapters and the
HTTP API talk to this service, never to each other directly.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Optional

from visual_studio.config import Settings
from visual_studio.domain.contracts import BatchRequest, BatchResponse
from visual_studio.domain.models import GenerationTask, TaskStatus
from visual_studio.events.bus import EventBus
from visual_studio.logging_config import get_logger
from visual_studio.persistence.sqlite import SqliteStore
from visual_studio.planner.planner import Planner
from visual_studio.providers.dashscope import DashScopeImageProvider
from visual_studio.providers.gpt_image import GptImageProvider
from visual_studio.providers.mock import MockProvider
from visual_studio.providers.seedream import SeedreamProvider
from visual_studio.quality.alignment import AlignmentChecker
from visual_studio.quality.checker import QualityChecker
from visual_studio.queue.scheduler import PriorityScheduler

logger = get_logger()


class GenerationService:
    """Coordinates planning, queuing, generation, QA and eventing."""

    def __init__(self, config: Settings) -> None:
        self.config = config

        self.store = SqliteStore(config.db_path)
        self.store.init_schema()

        self.scheduler = PriorityScheduler(self.store)
        self.planner = Planner()
        self.quality = QualityChecker()
        self.alignment = AlignmentChecker()
        self.bus = EventBus(webhook_url=config.webhook_url, store=self.store)

        self.providers = {
            "mock": MockProvider(config.output_dir),
            "dashscope": DashScopeImageProvider(
                api_key=config.dashscope_api_key or None,
                base_url=config.dashscope_base_url,
                model=config.image_model,
                output_dir=config.output_dir,
                timeout=config.image_timeout,
            ),
            "seedream": SeedreamProvider(api_key=config.seedream_api_key or None),
            "gpt_image": GptImageProvider(),
        }

        self._worker_stop = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    # -- submission -----------------------------------------------------
    def submit_batch(self, request: BatchRequest) -> BatchResponse:
        """Plan a batch and enqueue one task per planned image."""
        plans = self.planner.plan(request)
        task_ids: list[str] = []

        for plan in plans:
            task = GenerationTask(
                task_id=uuid.uuid4().hex,
                case_id=request.case_id,
                platform=request.platform,
                image_type=plan.image_type,
                canvas=plan.canvas,
                selling_point=plan.selling_point,
                product_name=request.category_spec.product_name,
                required_elements=plan.required_elements,
                forbidden_elements=plan.forbidden_elements,
                style_preset=plan.style_preset,
                priority=plan.priority,
                prompt=self._build_prompt(plan),
            )
            self.scheduler.submit(task)
            self._emit("task.created", self._payload(task))
            task_ids.append(task.task_id)

        return BatchResponse(
            batch_id=uuid.uuid4().hex,
            task_ids=task_ids,
            status="accepted",
        )

    # -- reads ----------------------------------------------------------
    def get_task(self, task_id: str) -> Optional[GenerationTask]:
        return self.store.get_task(task_id)

    # -- processing -----------------------------------------------------
    def run_pending(self) -> int:
        """Process every currently-queued task. Returns count processed."""
        processed = 0
        while True:
            task = self.scheduler.next_task()
            if task is None:
                break
            self._process(task)
            processed += 1
        return processed

    def _process(self, task: GenerationTask) -> None:
        task = self.scheduler.mark_generating(task.task_id)
        self._emit("task.generating", self._payload(task))
        try:
            provider = self._provider_for(task.image_type)
            result = provider.generate(task)
            report = self.quality.check(task, result)
            alignment = self.alignment.check(task, result)
            image_url = result.metadata.get("image_url") or f"/outputs/{task.task_id}.svg"
            # The mock writes SVG; real providers write PNG. Keep the fallback
            # honest by deriving the extension from the artifact path.
            if result.image_path and not result.metadata.get("image_url"):
                ext = result.image_path.rsplit(".", 1)[-1].lower()
                image_url = f"/outputs/{task.task_id}.{ext}"
            task = self.scheduler.mark_succeeded(
                task.task_id,
                image_url=image_url,
                provider=provider.name,
                quality_flags=report.flags,
            )
            task.alignment_score = alignment.score
            task.alignment_flags = alignment.flags
            self.store.save_task(task)
            self._emit(
                "task.succeeded",
                self._payload(task, quality_flags=report.flags),
            )
        except Exception as exc:  # noqa: BLE001 - record any failure as task failure
            logger.exception("task %s failed", task.task_id)
            task = self.scheduler.mark_failed(task.task_id, str(exc))
            self._emit("task.failed", self._payload(task))

    # -- routing --------------------------------------------------------
    def _provider_for(self, image_type: str):
        route_map = self.config.provider_route_map
        name = route_map.get(image_type, self.config.provider)
        provider = self.providers.get(name)
        if provider is None:
            logger.warning("unknown provider %r; falling back to mock", name)
            provider = self.providers["mock"]
        return provider

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _build_prompt(plan) -> str:
        parts = [plan.selling_point]
        if plan.required_elements:
            parts.append("elements: " + ", ".join(plan.required_elements))
        parts.append(f"style: {plan.style_preset}")
        parts.append(f"type: {plan.image_type}")
        return "; ".join(parts)

    @staticmethod
    def _payload(task: GenerationTask, **extra: Any) -> dict[str, Any]:
        payload = {
            "task_id": task.task_id,
            "case_id": task.case_id,
            "status": task.status.value,
            "image_type": task.image_type,
            "image_url": task.image_url,
            "carries_selling_point": task.selling_point,
            "provider": task.provider,
            "error": task.error,
        }
        if "quality_flags" in extra:
            payload["quality_flags"] = extra["quality_flags"]
        return payload

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.bus.publish(event_type, payload)

    # -- startup recovery ----------------------------------------------
    def reconcile(self) -> int:
        """Restart recovery: re-enqueue dangling tasks. Returns count reset."""
        return self.scheduler.reconcile_on_startup()

    # -- background worker ---------------------------------------------
    def start_worker(self) -> None:
        """Start the background worker thread that drains the queue."""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        self._worker_stop.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="vs-worker", daemon=True
        )
        self._worker_thread.start()

    def stop_worker(self) -> None:
        self._worker_stop.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
        self._worker_thread = None

    def _worker_loop(self) -> None:
        while not self._worker_stop.is_set():
            try:
                self.run_pending()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("worker loop error: %s", exc)
            self._worker_stop.wait(0.5)
