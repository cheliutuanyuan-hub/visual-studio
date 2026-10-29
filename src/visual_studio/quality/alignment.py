"""Content-alignment scoring (metadata-grounded, deterministic).

Honest scope: like QualityChecker this is metadata-level alignment, not
pixel-level CV. It scores how much of the requested selling-point/element
constraints the artifact's recorded metadata actually carries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from visual_studio.domain.models import GenerationResult, GenerationTask


@dataclass
class AlignmentReport:
    score: float  # 0.0 - 1.0
    flags: list[str] = field(default_factory=list)


class AlignmentChecker:
    """Scores element-carrying alignment for a generated artifact."""

    def check(self, task: GenerationTask, result: GenerationResult) -> AlignmentReport:
        flags: list[str] = []
        metadata = result.metadata or {}

        # 1) required elements actually recorded as present
        requested = list(task.required_elements)
        present = list(metadata.get("required_elements_present") or [])
        hits = sum(1 for el in requested if el in present)
        coverage = (hits / len(requested)) if requested else 1.0

        # 2) selling point must appear in prompt + recorded elements
        sp = (task.selling_point or "").strip()
        sp_hit = bool(sp) and (sp in task.prompt or sp in present)
        if sp_hit:
            flags.append("selling_point:carried")
        else:
            flags.append("selling_point:missing")

        # 3) forbidden leakage penalty
        blob = " ".join([task.prompt, str(metadata)])
        leaked = [t for t in task.forbidden_elements if t and t in blob]

        # score: coverage dominates; sp penalty 0.3; forbidden leakage 0.2 each
        score = coverage
        if not sp_hit:
            score -= 0.3
        score -= 0.2 * len(leaked)
        score = max(0.0, min(1.0, round(score, 3)))

        if coverage < 1.0:
            flags.append(f"required:coverage:{coverage}")
        for t in leaked:
            flags.append(f"forbidden:present:{t}")
        return AlignmentReport(score=score, flags=flags)
