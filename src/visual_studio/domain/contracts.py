"""Pydantic request/response contracts (the HTTP API surface).

These schemas are the stable cross-project contract consumed by Project A's
``VisualAgent``. Endpoints never leak internal dataclasses; they speak these.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CategorySpec(BaseModel):
    """Category-level constraints shared by all images in a case."""

    category: str
    # Human-readable product the images depict (e.g. "夏季纯棉短袖T恤").
    # Optional so older callers keep working, but a real image provider needs
    # it: selling points alone ("100% cotton") do not identify the product.
    product_name: str = ""
    canvas_presets: dict[str, str] = Field(default_factory=dict)
    forbidden_terms: list[str] = Field(default_factory=list)


class ImageSpec(BaseModel):
    """A single image requested explicitly by the caller (optional)."""

    image_type: str
    canvas: str
    selling_point: str
    required_elements: list[str] = Field(default_factory=list)
    forbidden_elements: list[str] = Field(default_factory=list)
    style_preset: str = "default"
    priority: int = 10


class BatchRequest(BaseModel):
    """Structured batch submission for one ``case_id``.

    If ``images`` is empty, the planner synthesizes a default plan (one main,
    one scene, one detail) from the selling points and canvas presets.
    """

    case_id: str
    platform: str
    category_spec: CategorySpec
    selling_points: list[str] = Field(default_factory=list)
    images: list[ImageSpec] = Field(default_factory=list)


class BatchResponse(BaseModel):
    """202 Accepted response for a batch submission."""

    batch_id: str
    task_ids: list[str]
    status: str = "accepted"


class TaskView(BaseModel):
    """Read model returned by ``GET /v1/tasks/{task_id}``."""

    task_id: str
    status: str
    image_type: str
    image_url: Optional[str] = None
    carries_selling_point: str
    quality_flags: list[str] = Field(default_factory=list)
    alignment: Optional[dict] = None  # {"score": float, "flags": [...]}
    provider: Optional[str] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
