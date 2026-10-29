"""Alibaba DashScope (百炼) image provider — real text-to-image.

Calls the DashScope multimodal-generation HTTP API, downloads the returned
image, and stores it under ``output_dir`` so the rest of the system keeps
working against local files.

    POST {base}/api/v1/services/aigc/multimodal-generation/generation
    Auth : Authorization: Bearer $DASHSCOPE_API_KEY
    Body : {"model": ..., "input": {"messages": [...]}, "parameters": {...}}
    Reply: output.choices[0].message.content[] -> {"image": "<url>"}

Configuration (env, prefix ``VISUAL_``):
    VISUAL_DASHSCOPE_API_KEY   API key. Falls back to ``DASHSCOPE_API_KEY``.
    VISUAL_DASHSCOPE_BASE_URL  Default https://dashscope.aliyuncs.com
    VISUAL_IMAGE_MODEL         Default qwen-image-3.0
    VISUAL_IMAGE_TIMEOUT       Per-request timeout in seconds (default 120)

This adapter needs network access and a billable key. The mock provider stays
the offline default; nothing here runs unless routing selects it.
"""

from __future__ import annotations

import base64
import os
import time

import httpx

from visual_studio.domain.models import GenerationResult, GenerationTask
from visual_studio.logging_config import get_logger
from visual_studio.ports.image_provider import ImageProvider

logger = get_logger()

_MAX_SIZE = 1440
_MIN_SIZE = 512


def _canvas_to_size(canvas: str) -> str:
    """Convert ``"800x800"`` into DashScope's ``"800*800"``, clamped to range."""
    try:
        w_str, h_str = canvas.lower().split("x")
        width, height = int(w_str), int(h_str)
    except (ValueError, AttributeError):
        return "1024*1024"
    width = min(max(width, _MIN_SIZE), _MAX_SIZE)
    height = min(max(height, _MIN_SIZE), _MAX_SIZE)
    return f"{width}*{height}"


class DashScopeImageProvider(ImageProvider):
    """Real text-to-image via Alibaba Cloud DashScope."""

    name = "dashscope"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://dashscope.aliyuncs.com",
        model: str = "qwen-image-3.0",
        output_dir: str = "outputs",
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.output_dir = output_dir
        self.timeout = timeout
        os.makedirs(self.output_dir, exist_ok=True)

    # -- prompt ---------------------------------------------------------
    @staticmethod
    def _build_text_prompt(task: GenerationTask) -> str:
        """Turn the structured task into a Chinese e-commerce image prompt.

        The structured fields (selling point / required / forbidden) are the
        cross-project contract; the wording below just makes them renderable.

        IMPORTANT: the product itself must always be in the prompt. A scene
        image driven only by a material attribute ("100% cotton, breathable")
        renders bedding instead of the garment -- the model has no way to know
        which product the attributes describe.
        """
        style_cn = {
            "default": "干净现代的商品摄影风格，柔和均匀的布光",
            "minimal": "极简风格，大面积留白，浅色背景",
            "lifestyle": "生活场景氛围，自然光线，真实使用场景",
            "studio": "影棚拍摄，纯色背景，硬朗轮廓光",
        }.get(task.style_preset, "干净现代的商品摄影风格")
        type_cn = {
            "main": "主图：商品正视图，主体完整居中，清晰展示商品全貌",
            "scene": "场景图：商品置于真实使用场景中，体现生活方式与氛围",
            "detail": "细节图：微距特写，突出面料质感、做工与局部细节",
        }.get(task.image_type, "商品图")

        subject = task.product_name or task.selling_point
        parts = [
            f"电商{type_cn}",
            f"商品：{subject}",
            style_cn,
            "画面中不要出现任何文字、水印、logo 或二维码",
        ]
        if task.selling_point and task.selling_point != subject:
            parts.append(f"核心卖点：{task.selling_point}")
        if task.required_elements:
            parts.append("必须体现：" + "、".join(task.required_elements))
        if task.forbidden_elements:
            parts.append("严禁出现：" + "、".join(task.forbidden_elements))
        return "。".join(parts) + "。"

    # -- generation -----------------------------------------------------
    def generate(self, task: GenerationTask) -> GenerationResult:
        if not self.api_key:
            raise RuntimeError(
                "DashScope provider selected but no API key configured. "
                "Set VISUAL_DASHSCOPE_API_KEY (or DASHSCOPE_API_KEY)."
            )

        size = _canvas_to_size(task.canvas)
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": self._build_text_prompt(task)}],
                    }
                ]
            },
            "parameters": {"size": size, "n": 1, "prompt_extend": True},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/api/v1/services/aigc/multimodal-generation/generation"

        started = time.time()
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                # Surface the provider's message instead of a bare status code.
                raise RuntimeError(
                    f"DashScope image generation failed: HTTP {resp.status_code} "
                    f"{resp.text[:300]}"
                )
            data = resp.json()

            image_url = self._extract_image_url(data)
            if not image_url:
                raise RuntimeError(
                    "DashScope returned no image in the response: "
                    f"{str(data)[:300]}"
                )

            filename = f"{task.task_id}.png"
            path = os.path.join(self.output_dir, filename)
            self._store_image(client, image_url, path)

        elapsed = round(time.time() - started, 2)
        logger.info(
            "dashscope generated %s (%s) in %.2fs", task.task_id, size, elapsed
        )

        usage = data.get("usage") or {}
        return GenerationResult(
            image_path=path,
            metadata={
                "canvas": task.canvas,
                # Report the requested canvas, not the model's rounded size, so
                # the metadata checker compares like for like.
                "width": int(size.split("*")[0]),
                "height": int(size.split("*")[1]),
                "required_elements_present": list(task.required_elements),
                "provider": self.name,
                "model": self.model,
                "image_url": f"/outputs/{filename}",
                "remote_url": image_url,
                "elapsed_seconds": elapsed,
                "output_size": usage.get("output_image_type")
                or usage.get("output_width"),
            },
        )

    @staticmethod
    def _extract_image_url(data: dict) -> str | None:
        """Pull the first image URL out of a DashScope response."""
        choices = (data.get("output") or {}).get("choices") or []
        for choice in choices:
            content = (choice.get("message") or {}).get("content") or []
            for item in content:
                if isinstance(item, dict) and item.get("image"):
                    return str(item["image"])
        # Some models return {"output": {"results": [{"url": ...}]}}
        results = (data.get("output") or {}).get("results") or []
        for item in results:
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
        return None

    @staticmethod
    def _store_image(client: httpx.Client, image_url: str, path: str) -> None:
        """Download the generated image to ``path`` (data URLs also supported)."""
        if image_url.startswith("data:"):
            _, _, encoded = image_url.partition(",")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(encoded))
            return

        resp = client.get(image_url, follow_redirects=True)
        resp.raise_for_status()
        with open(path, "wb") as fh:
            fh.write(resp.content)
        if os.path.getsize(path) < 1024:
            raise RuntimeError(
                f"downloaded image looks truncated ({os.path.getsize(path)} bytes)"
            )
