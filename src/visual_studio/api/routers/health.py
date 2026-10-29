"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from visual_studio.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe consumed by orchestrators and container platforms."""
    return HealthResponse(status="ok")
