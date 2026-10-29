"""End-to-end verification harness for visual-studio.

Runs the full pipeline offline (mock provider) and asserts real artifacts are
produced. Prints exactly ``VERIFICATION PASSED`` and exits 0 on success.

Usage:
    python demo.py
"""

import os
import sys
import tempfile

# Make the src-layout package importable without installation.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "src"))

from visual_studio.config import Settings  # noqa: E402
from visual_studio.domain.contracts import (  # noqa: E402
    BatchRequest,
    CategorySpec,
    ImageSpec,
)
from visual_studio.domain.models import TaskStatus  # noqa: E402
from visual_studio.service.generation_service import GenerationService  # noqa: E402


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="vs_demo_")
    cfg = Settings(
        db_path=os.path.join(tmp, "demo.db"),
        output_dir=os.path.join(tmp, "outputs"),
        provider="mock",
        provider_route='{"main":"mock","scene":"mock","detail":"mock"}',
        webhook_url=None,
        host="127.0.0.1",
        port=0,
    )
    service = GenerationService(cfg)

    request = BatchRequest(
        case_id="demo_case",
        platform="tmall",
        category_spec=CategorySpec(
            category="kitchen",
            canvas_presets={"main": "800x800", "scene": "1200x800", "detail": "800x800"},
            forbidden_terms=["最", "第一"],
        ),
        selling_points=["便携", "USB充电"],
        images=[
            ImageSpec(
                image_type="main",
                canvas="800x800",
                selling_point="便携",
                required_elements=["榨汁杯", "水果"],
                forbidden_elements=["文字logo"],
                style_preset="default",
            )
        ],
    )

    response = service.submit_batch(request)
    assert response.task_ids, "submit_batch produced no tasks"
    assert response.status == "accepted"

    # Process everything synchronously (no server needed).
    processed = service.run_pending()
    assert processed == len(response.task_ids), f"processed {processed}"

    for task_id in response.task_ids:
        task = service.get_task(task_id)
        assert task is not None, f"task {task_id} missing"
        assert task.status == TaskStatus.SUCCEEDED, (
            f"task {task_id} status={task.status.value} error={task.error}"
        )
        assert task.provider == "mock"
        assert task.image_url and task.image_url.endswith(".svg")

        # T1: content-alignment score must be present and full (mock records
        # every required element and the selling point is carried).
        assert task.alignment_score is not None
        assert task.alignment_score == 1.0
        assert "selling_point:carried" in task.alignment_flags

        svg_path = os.path.join(cfg.output_dir, f"{task_id}.svg")
        assert os.path.exists(svg_path), f"SVG not written: {svg_path}"
        with open(svg_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "MOCK PROVIDER" in content
        assert task.selling_point in content
        assert "800x800" in content
        for element in task.required_elements:
            assert element in content

    # Confirm a structured event was persisted for the case.
    events = service.store.get_events("demo_case")
    assert events, "no events persisted"
    assert any(e["event_type"] == "task.succeeded" for e in events)

    print("VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
