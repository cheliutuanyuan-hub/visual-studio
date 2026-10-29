"""Priority scheduler / queue.

Owns the queueing semantics over the persistence layer:
  * ``submit`` enqueues a task (``queued``).
  * ``next_task`` peeks the highest-priority ``queued`` task (does NOT mutate).
  * ``mark_generating`` / ``mark_succeeded`` / ``mark_failed`` drive state.
  * ``reconcile_on_startup`` resets any ``queued``/``generating`` task back to
    ``queued`` so a restarted process re-runs them. This is safe here because
    the default provider is a mock (no shared external GPU job to clobber).

Higher ``priority`` wins; ties break on creation time (FIFO within a priority).
"""

from __future__ import annotations

from typing import Optional

from visual_studio.domain.models import GenerationTask, TaskStatus
from visual_studio.persistence.sqlite import SqliteStore


class PriorityScheduler:
    """Priority queue + batch coordination over a :class:`SqliteStore`."""

    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def submit(self, task: GenerationTask) -> GenerationTask:
        """Enqueue a task."""
        task.status = TaskStatus.QUEUED
        self.store.save_task(task)
        return task

    def next_task(self) -> Optional[GenerationTask]:
        """Return the highest-priority ``queued`` task, or ``None``."""
        return self.store.get_highest_priority_queued()

    def mark_generating(self, task_id: str) -> Optional[GenerationTask]:
        task = self.store.get_task(task_id)
        if task is None:
            return None
        task.status = TaskStatus.GENERATING
        self.store.save_task(task)
        return task

    def mark_succeeded(
        self,
        task_id: str,
        image_url: Optional[str] = None,
        provider: Optional[str] = None,
        quality_flags: Optional[list[str]] = None,
    ) -> Optional[GenerationTask]:
        task = self.store.get_task(task_id)
        if task is None:
            return None
        task.status = TaskStatus.SUCCEEDED
        task.image_url = image_url
        task.provider = provider
        task.quality_flags = quality_flags or []
        task.error = None
        self.store.save_task(task)
        return task

    def mark_failed(
        self, task_id: str, error: str
    ) -> Optional[GenerationTask]:
        task = self.store.get_task(task_id)
        if task is None:
            return None
        task.status = TaskStatus.FAILED
        task.error = error
        self.store.save_task(task)
        return task

    def reconcile_on_startup(self) -> int:
        """Reset dangling ``queued``/``generating`` tasks to ``queued``.

        Returns the number of tasks that were reset. Safe under the mock
        provider (no external GPU work is abandoned mid-flight).
        """
        reset = 0
        for task in self.store.list_tasks():
            if task.status in (TaskStatus.QUEUED, TaskStatus.GENERATING):
                task.status = TaskStatus.QUEUED
                self.store.save_task(task)
                reset += 1
        return reset
