"""Mock image provider (default, fully functional, OFFLINE).

It writes a real, self-describing SVG file to the output directory for every
task. The SVG embeds the prompt, the required elements, the canvas size and a
``MOCK PROVIDER`` label, proving a genuine artifact is produced on disk without
any GPU, network or external service.
"""

from __future__ import annotations

import html
import os

from visual_studio.domain.models import GenerationResult, GenerationTask
from visual_studio.ports.image_provider import ImageProvider


def _split_canvas(canvas: str) -> tuple[int, int]:
    """Parse a ``WxH`` canvas string into (width, height)."""
    try:
        w_str, h_str = canvas.lower().split("x")
        return int(w_str), int(h_str)
    except (ValueError, AttributeError):
        return 800, 800


class MockProvider(ImageProvider):
    name = "mock"

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, task: GenerationTask) -> GenerationResult:
        width, height = _split_canvas(task.canvas)
        filename = f"{task.task_id}.svg"
        path = os.path.join(self.output_dir, filename)

        svg = self._render_svg(task, width, height)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)

        # The mock records every required element as present (honest metadata:
        # the file genuinely contains the element labels). Pixel-level presence
        # is NOT verified - this is metadata QA, not computer vision.
        metadata = {
            "canvas": task.canvas,
            "width": width,
            "height": height,
            "required_elements_present": list(task.required_elements),
            "provider": self.name,
            "image_url": f"/outputs/{filename}",
        }
        return GenerationResult(image_path=path, metadata=metadata)

    @staticmethod
    def _render_svg(task: GenerationTask, width: int, height: int) -> str:
        """Build an SVG document containing the task's structured fields."""
        prompt = html.escape(task.prompt)
        required_items = "".join(
            f'<li>{html.escape(el)}</li>' for el in task.required_elements
        )
        forbidden_items = "".join(
            f'<li>{html.escape(el)}</li>' for el in task.forbidden_elements
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f4f4f5"/>
  <rect x="8" y="8" width="{width - 16}" height="{height - 16}" fill="none" stroke="#3b82f6" stroke-width="2"/>
  <text x="20" y="40" font-family="sans-serif" font-size="20" fill="#111827">MOCK PROVIDER</text>
  <text x="20" y="72" font-family="sans-serif" font-size="14" fill="#374151">case: {html.escape(task.case_id)}</text>
  <text x="20" y="96" font-family="sans-serif" font-size="14" fill="#374151">type: {html.escape(task.image_type)}</text>
  <text x="20" y="120" font-family="sans-serif" font-size="14" fill="#374151">canvas: {html.escape(task.canvas)}</text>
  <text x="20" y="148" font-family="sans-serif" font-size="14" fill="#374151">prompt: {prompt}</text>
  <text x="20" y="180" font-family="sans-serif" font-size="14" fill="#065f46">required:</text>
  <text x="40" y="200" font-family="sans-serif" font-size="13" fill="#065f46"><ul>{required_items}</ul></text>
  <text x="20" y="232" font-family="sans-serif" font-size="14" fill="#7f1d1d">forbidden:</text>
  <text x="40" y="252" font-family="sans-serif" font-size="13" fill="#7f1d1d"><ul>{forbidden_items}</ul></text>
</svg>
"""
