"""Task status + Server-Sent-Events stream endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from visual_studio.api.schemas import TaskView
from visual_studio.domain.models import TaskStatus

router = APIRouter(prefix="/v1", tags=["tasks"])


@router.get("/tasks/{task_id}", response_model=TaskView)
def get_task(task_id: str, request: Request) -> TaskView:
    """Return the current state of a single task."""
    service = request.app.state.service
    task = service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    return TaskView(
        task_id=task.task_id,
        status=task.status.value,
        image_type=task.image_type,
        image_url=task.image_url,
        carries_selling_point=task.selling_point,
        quality_flags=list(task.quality_flags),
        alignment={"score": task.alignment_score, "flags": task.alignment_flags}
        if task.alignment_score is not None
        else None,
        provider=task.provider,
        error=task.error,
    )


@router.get("/events/stream")
async def event_stream(case_id: str, request: Request) -> StreamingResponse:
    """Stream ``data: {json}`` SSE lines for a case's events.

    Reads persisted events (emitted by the service) filtered by ``case_id`` and
    pushes any new ones as they arrive. The connection stays open until the
    client disconnects.
    """
    service = request.app.state.service
    store = service.store

    async def generator():
        last_id = 0
        while True:
            if await request.is_disconnected():
                break
            events = store.get_events(case_id, since_id=last_id)
            for event in events:
                last_id = event["id"]
                yield f"data: {event['payload']}\n\n"
            # Small poll interval keeps the stream responsive but cheap.
            await asyncio.sleep(0.3)

    return StreamingResponse(generator(), media_type="text/event-stream")
