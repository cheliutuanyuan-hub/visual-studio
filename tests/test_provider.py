"""Tests for the MockProvider (real artifact on disk)."""

import json
import os
import tempfile

from visual_studio.domain.models import GenerationTask
from visual_studio.providers.mock import MockProvider


def _task(task_id="t1"):
    return GenerationTask(
        task_id=task_id,
        case_id="c1",
        platform="tmall",
        image_type="main",
        canvas="800x800",
        selling_point="便携",
        required_elements=["榨汁杯", "水果"],
        forbidden_elements=[],
        style_preset="default",
        priority=10,
        prompt="便携; elements: 榨汁杯, 水果; style: default; type: main",
    )


def test_mock_provider_writes_real_svg_file():
    tmp = tempfile.mkdtemp()
    provider = MockProvider(tmp)
    result = provider.generate(_task())

    assert result.image_path is not None
    assert os.path.exists(result.image_path)
    assert result.image_path.endswith(".svg")


def test_svg_contains_structured_fields():
    tmp = tempfile.mkdtemp()
    provider = MockProvider(tmp)
    result = provider.generate(_task())

    with open(result.image_path, encoding="utf-8") as fh:
        content = fh.read()

    assert "MOCK PROVIDER" in content
    assert "便携" in content
    assert "800x800" in content
    assert "榨汁杯" in content and "水果" in content


def test_mock_provider_records_required_elements_present():
    tmp = tempfile.mkdtemp()
    provider = MockProvider(tmp)
    result = provider.generate(_task())

    present = result.metadata.get("required_elements_present")
    assert present == ["榨汁杯", "水果"]
    assert result.metadata.get("canvas") == "800x800"
    assert result.metadata.get("image_url") == "/outputs/t1.svg"
