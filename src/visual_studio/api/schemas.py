"""API schemas.

The API reads/writes the domain contracts. This module simply re-exports the
canonical Pydantic contracts so routers and external callers have a single
import surface.
"""

from __future__ import annotations

from visual_studio.domain.contracts import (  # noqa: F401
    BatchRequest,
    BatchResponse,
    CategorySpec,
    HealthResponse,
    ImageSpec,
    TaskView,
)

__all__ = [
    "BatchRequest",
    "BatchResponse",
    "CategorySpec",
    "HealthResponse",
    "ImageSpec",
    "TaskView",
]
