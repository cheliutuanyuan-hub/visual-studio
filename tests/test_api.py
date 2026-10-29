"""End-to-end API tests using FastAPI's TestClient (lifespan + worker)."""

import json
import os
import socket
import tempfile
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from visual_studio.api.app import create_app
from visual_studio.config import Settings
from visual_studio.service.generation_service import GenerationService


def _make_service():
    tmp = tempfile.mkdtemp(prefix="vs_api_")
    cfg = Settings(
        db_path=os.path.join(tmp, "api.db"),
        output_dir=os.path.join(tmp, "outputs"),
        provider="mock",
        provider_route='{"main":"mock","scene":"mock","detail":"mock"}',
        webhook_url=None,
        host="127.0.0.1",
        port=0,
    )
    return GenerationService(cfg)


BATCH = {
    "case_id": "api_case_1",
    "platform": "tmall",
    "category_spec": {
        "category": "kitchen",
        "canvas_presets": {"main": "800x800", "scene": "1200x800", "detail": "800x800"},
        "forbidden_terms": ["最", "第一"],
    },
    "selling_points": ["便携", "USB充电"],
    "images": [
        {
            "image_type": "main",
            "canvas": "800x800",
            "selling_point": "便携",
            "required_elements": ["榨汁杯", "水果"],
            "forbidden_elements": ["文字logo"],
            "style_preset": "default",
        }
    ],
}


def test_health():
    svc = _make_service()
    with TestClient(create_app(svc)) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_batch_endpoint_returns_task_ids():
    svc = _make_service()
    with TestClient(create_app(svc)) as client:
        resp = client.post("/v1/generate/batch", json=BATCH)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert isinstance(body["task_ids"], list)
        assert len(body["task_ids"]) == 1
        assert "batch_id" in body


def test_task_reaches_succeeded_and_svg_written():
    svc = _make_service()
    with TestClient(create_app(svc)) as client:
        resp = client.post("/v1/generate/batch", json=BATCH)
        task_id = resp.json()["task_ids"][0]

        # Poll until the background worker turns it to "succeeded".
        final = None
        for _ in range(100):
            tr = client.get(f"/v1/tasks/{task_id}")
            assert tr.status_code == 200
            final = tr.json()
            if final["status"] == "succeeded":
                break
            time.sleep(0.1)

        assert final["status"] == "succeeded"
        assert final["provider"] == "mock"
        assert final["image_url"].endswith(".svg")
        assert final["carries_selling_point"] == "便携"
        assert "required:榨汁杯" in final["quality_flags"]
        assert "required:水果" in final["quality_flags"]

        # The artifact must physically exist on disk.
        svg_path = os.path.join(svc.config.output_dir, f"{task_id}.svg")
        assert os.path.exists(svg_path)


def test_event_stream_emits_structured_events():
    """SSE endpoint test over a real socket (the true production path).

    In-process transports (starlette TestClient, httpx ASGITransport) hang on
    an intentionally infinite SSE generator in this dependency set, so this
    test runs the app under uvicorn on an ephemeral port and streams over real
    TCP — where client disconnect is real and the generator exits cleanly.
    """
    import uvicorn

    svc = _make_service()
    app = create_app(svc)

    # Grab a free port, then let uvicorn bind it (tiny race, fine for tests).
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 10.0
        while True:
            try:
                httpx.get(f"{base}/health", timeout=1.0)
                break
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(0.1)

        with httpx.Client(base_url=base, timeout=10.0) as client:
            resp = client.post("/v1/generate/batch", json=BATCH)
            assert resp.status_code == 202
            case_id = BATCH["case_id"]

            seen = []
            with client.stream("GET", f"/v1/events/stream?case_id={case_id}") as stream:
                assert stream.status_code == 200
                for line in stream.iter_lines():
                    if line.startswith("data: "):
                        payload = json.loads(line[len("data: "):])
                        seen.append(payload.get("status"))
                    if "succeeded" in seen or len(seen) >= 12:
                        break

            assert "queued" in seen or "accepted" in seen  # created/generating seen
            assert "succeeded" in seen
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
