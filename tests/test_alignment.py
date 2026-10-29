"""T1: content-alignment scoring (metadata-grounded, deterministic)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from visual_studio.api.app import create_app
from visual_studio.domain.models import GenerationResult, GenerationTask
from visual_studio.quality.alignment import AlignmentChecker

from .test_api import BATCH, _make_service


def _task(**overrides) -> GenerationTask:
    base = dict(
        task_id="t1",
        case_id="c1",
        platform="tmall",
        image_type="main",
        canvas="800x800",
        selling_point="便携",
        required_elements=["榨汁杯", "水果"],
        forbidden_elements=["文字logo"],
        prompt="便携; elements: 榨汁杯, 水果",
    )
    base.update(overrides)
    return GenerationTask(**base)


def test_alignment_full_coverage_scores_high():
    task = _task()
    result = GenerationResult(
        image_path="out.svg",
        metadata={"required_elements_present": ["榨汁杯", "水果"]},
    )
    report = AlignmentChecker().check(task, result)
    assert report.score == 1.0
    assert "selling_point:carried" in report.flags


def test_alignment_missing_element_penalizes():
    task = _task()
    result = GenerationResult(
        image_path="out.svg",
        metadata={"required_elements_present": ["榨汁杯"]},  # 1 of 2 present
    )
    report = AlignmentChecker().check(task, result)
    assert report.score < 1.0
    assert "required:coverage:0.5" in report.flags


def test_alignment_selling_point_missing_penalizes():
    task = _task(prompt="elements: 榨汁杯, 水果")  # selling point absent from prompt
    result = GenerationResult(
        image_path="out.svg",
        metadata={"required_elements_present": ["榨汁杯", "水果"]},
    )
    report = AlignmentChecker().check(task, result)
    assert report.score == 0.7  # coverage 1.0 minus 0.3 selling-point penalty
    assert "selling_point:missing" in report.flags


def test_task_view_contains_alignment():
    svc = _make_service()
    with TestClient(create_app(svc)) as client:
        resp = client.post("/v1/generate/batch", json=BATCH)
        assert resp.status_code == 202
        task_id = resp.json()["task_ids"][0]

        final = None
        for _ in range(100):
            tr = client.get(f"/v1/tasks/{task_id}")
            assert tr.status_code == 200
            final = tr.json()
            if final["status"] == "succeeded":
                break
            time.sleep(0.1)

        assert final["status"] == "succeeded"
        alignment = final["alignment"]
        assert alignment is not None
        assert alignment["score"] == 1.0
        assert "selling_point:carried" in alignment["flags"]
