"""OpenAI GPT-Image provider - structured STUB.

Intentionally NOT implemented. Documents the real endpoint/auth so a future
adapter can be dropped in behind the same port. The mock provider remains the
offline default.

Real integration notes (for the future adapter):
    Endpoint : POST https://api.openai.com/v1/images/generations
    Auth     : Bearer token via header `Authorization: Bearer <API_KEY>`
               (env OPENAI_API_KEY). Organization header optional.
    Payload  : {
                 "model": "gpt-image-1",
                 "prompt": "<text prompt>",
                 "size": "1024x1024",            # one of allowed sizes
                 "n": 1,
                 "response_format": "b64_json"   # or "url"
               }
    Response : { "data": [ { "b64_json": "..." } ] }
    Decode base64 and write the bytes under output_dir as <task_id>.png, then
    set task.image_url to the served path (e.g. /outputs/<task_id>.png).
"""

from __future__ import annotations

from visual_studio.domain.models import GenerationResult, GenerationTask
from visual_studio.ports.image_provider import ImageProvider


class GptImageProvider(ImageProvider):
    name = "gpt_image"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def generate(self, task: GenerationTask) -> GenerationResult:  # noqa: D401
        raise NotImplementedError(
            "GptImageProvider is a structured stub. Real adapter must call "
            "POST https://api.openai.com/v1/images/generations with Bearer "
            "auth (env OPENAI_API_KEY), decode b64_json, and store the file "
            "under output_dir. Offline builds use MockProvider instead."
        )
