"""Metadata-level quality checker.

IMPORTANT (honest scope): this is *metadata* QA, not pixel-level computer
vision. It verifies that:
  * the provider reported success (an artifact path exists),
  * the artifact's recorded canvas matches the requested preset,
  * every required element is recorded as present in the artifact metadata,
  * no forbidden term leaked into the prompt/metadata.

It does NOT inspect the actual pixels. That limitation is by design and is
documented in the README.
"""

from __future__ import annotations

import json

from visual_studio.domain.models import GenerationResult, GenerationTask, QualityReport


class QualityChecker:
    """Runs deterministic metadata checks and returns quality flags."""

    def check(self, task: GenerationTask, result: GenerationResult) -> QualityReport:
        flags: list[str] = []

        # 1. Provider success: a non-null artifact path means generation worked.
        if result.image_path:
            flags.append("provider:ok")
        else:
            flags.append("provider:missing")

        # 2. Canvas dimensions match the requested preset.
        recorded_canvas = result.metadata.get("canvas")
        if recorded_canvas == task.canvas:
            flags.append("canvas:ok")
        else:
            flags.append(f"canvas:mismatch:{recorded_canvas}")

        # 3. Required elements recorded as present in the artifact metadata.
        recorded_present = result.metadata.get("required_elements_present") or []
        for element in task.required_elements:
            if element in recorded_present:
                flags.append(f"required:{element}")
            else:
                flags.append(f"required:missing:{element}")

        # 4. Forbidden terms absent from prompt + metadata text.
        blob = " ".join(
            [
                task.prompt,
                json.dumps(result.metadata, ensure_ascii=False),
            ]
        )
        forbidden_hit = False
        for term in task.forbidden_elements:
            if term and term in blob:
                flags.append(f"forbidden:present:{term}")
                forbidden_hit = True
        if not forbidden_hit:
            flags.append("forbidden:absent")

        passed = (
            "provider:ok" in flags
            and "canvas:ok" in flags
            and not any(f.startswith("required:missing:") for f in flags)
            and not any(f.startswith("forbidden:present:") for f in flags)
        )
        return QualityReport(flags=flags, passed=passed)
