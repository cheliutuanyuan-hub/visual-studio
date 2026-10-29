"""Tests for the priority scheduler / queue semantics."""

import os
import tempfile

from visual_studio.domain.models import GenerationTask, TaskStatus
from visual_studio.persistence.sqlite import SqliteStore
from visual_studio.queue.scheduler import PriorityScheduler


def _make(case_id, tag, priority):
    return GenerationTask(
        task_id=f"{case_id}-{tag}",
        case_id=case_id,
        platform="tmall",
        image_type="main",
        canvas="800x800",
        selling_point="sp",
        required_elements=[],
        forbidden_elements=[],
        style_preset="default",
        priority=priority,
    )


def _store():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "queue.db")
    store = SqliteStore(path)
    store.init_schema()
    return store


def test_next_task_returns_highest_priority_first():
    store = _store()
    sched = PriorityScheduler(store)
    sched.submit(_make("c", "low", 1))
    sched.submit(_make("c", "high", 100))
    sched.submit(_make("c", "mid", 50))

    order = []
    while True:
        task = sched.next_task()
        if task is None:
            break
        sched.mark_generating(task.task_id)
        order.append(task.priority)

    assert order == [100, 50, 1]


def test_priority_tie_breaks_by_creation_order():
    store = _store()
    sched = PriorityScheduler(store)
    first = _make("c", "a", 10)
    second = _make("c", "b", 10)
    sched.submit(first)
    sched.submit(second)

    # next_task only peeks; the scheduler marks generating to dequeue,
    # mirroring the real worker flow (next_task -> mark_generating).
    t1 = sched.next_task()
    sched.mark_generating(t1.task_id)
    t2 = sched.next_task()
    assert t1.task_id == "c-a"
    assert t2.task_id == "c-b"


def test_reconcile_resets_generating_and_queued():
    store = _store()
    sched = PriorityScheduler(store)
    task = _make("c", "a", 10)
    sched.submit(task)

    # Simulate a crash mid-generation: task is stuck in "generating".
    sched.mark_generating(task.task_id)
    assert store.get_task(task.task_id).status == TaskStatus.GENERATING

    reset = sched.reconcile_on_startup()
    assert reset == 1
    assert store.get_task(task.task_id).status == TaskStatus.QUEUED


def test_empty_queue_returns_none():
    store = _store()
    sched = PriorityScheduler(store)
    assert sched.next_task() is None
