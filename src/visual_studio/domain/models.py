"""Core domain models for the generation service.

These are pure, framework-free dataclasses. They are the canonical in-memory
representation of a generation task and its result. Persistence converts to/from
SQLAlchemy rows; the API layer converts to/from Pydantic contracts. Keeping the
domain free of framework types is the heart of the hexagonal design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    """Lifecycle states of a generation task."""

    QUEUED = "queued"
    GENERATING = "generating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value


@dataclass
class GenerationTask:
    """A single constrained image-generation task belonging to a case.

    ``priority`` is an integer; higher means more urgent. The scheduler always
    dequeues the highest-priority ``queued`` task first.
    """

    task_id: str
    case_id: str
    platform: str
    image_type: str  # one of: main | scene | detail (extensible)
    canvas: str  # "WxH" e.g. "800x800"
    selling_point: str
    # What the image actually depicts. Real providers must know it; an
    # attribute-only prompt ("100% cotton") renders the wrong subject.
    product_name: str = ""
    required_elements: list[str] = field(default_factory=list)
    forbidden_elements: list[str] = field(default_factory=list)
    style_preset: str = "default"
    priority: int = 10
    # Text prompt handed to the provider (built by the planner/service).
    prompt: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    image_url: Optional[str] = None
    provider: Optional[str] = None
    quality_flags: list[str] = field(default_factory=list)
    alignment_score: Optional[float] = None
    alignment_flags: list[str] = field(default_factory=list)
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (status -> string)."""
        return {
            "task_id": self.task_id,
            "case_id": self.case_id,
            "platform": self.platform,
            "image_type": self.image_type,
            "canvas": self.canvas,
            "selling_point": self.selling_point,
            "product_name": self.product_name,
            "required_elements": list(self.required_elements),
            "forbidden_elements": list(self.forbidden_elements),
            "style_preset": self.style_preset,
            "priority": self.priority,
            "prompt": self.prompt,
            "status": self.status.value,
            "image_url": self.image_url,
            "provider": self.provider,
            "quality_flags": list(self.quality_flags),
            "alignment_score": self.alignment_score,
            "alignment_flags": list(self.alignment_flags),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class GenerationResult:
    """The artifact produced by a provider for a single task."""

    image_path: Optional[str]  # absolute path on disk (or None on failure)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImagePlan:
    """A planned image derived by the planner from the structured request."""

    image_type: str
    canvas: str
    selling_point: str
    required_elements: list[str]
    forbidden_elements: list[str]
    style_preset: str
    priority: int


@dataclass
class QualityReport:
    """Result of metadata-level QA on a generated artifact."""

    flags: list[str]
    passed: bool
