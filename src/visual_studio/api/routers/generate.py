"""Batch generation endpoint (the Project A ingest contract)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from visual_studio.api.schemas import BatchRequest, BatchResponse

router = APIRouter(prefix="/v1", tags=["generate"])


@router.post("/generate/batch", response_model=BatchResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_batch(payload: BatchRequest, request: Request) -> BatchResponse:
    """Submit a structured batch; returns 202 with task ids.

    The background worker drains the queue, so tasks typically reach
    ``succeeded`` within moments of this call.
    """
    service = request.app.state.service
    return service.submit_batch(payload)
