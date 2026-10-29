"""Seedream (Volcengine/ByteDance) image provider - structured STUB.

This is intentionally NOT implemented. It exists so the wiring, routing and
queueing logic can be exercised end-to-end, and documents exactly what the real
adapter must do. The mock provider remains the offline default.

Real integration notes (for the future adapter):
    Endpoint : POST https://visual.volcengineapi.com/api/v1/images/generations
    Auth     : API key via header `X-Api-Key` (or signed request per Volcengine
               signing V4). Configure via env SEEDREAM_API_KEY.
    Payload  : {
                 "model": "general_v2.1_L",   # or seedream-3.0 etc.
                 "prompt": "<text prompt>",
                 "width":  <int>,
                 "height": <int>,
                 "n": 1
               }
    Response : { "data": [ { "url": "<image url>" } ] }
    You must download the returned URL and store it under output_dir, then set
    task.image_url to the served path (e.g. /outputs/<task_id>.png).
"""

from __future__ import annotations

from visual_studio.domain.models import GenerationResult, GenerationTask
from visual_studio.ports.image_provider import ImageProvider


class SeedreamProvider(ImageProvider):
    name = "seedream"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def generate(self, task: GenerationTask) -> GenerationResult:  # noqa: D401
        raise NotImplementedError(
            "SeedreamProvider is a structured stub. Real adapter must call "
            "POST https://visual.volcengineapi.com/api/v1/images/generations "
            "with X-Api-Key auth (env SEEDREAM_API_KEY) and download the "
            "returned image URL. Offline builds use MockProvider instead."
        )
