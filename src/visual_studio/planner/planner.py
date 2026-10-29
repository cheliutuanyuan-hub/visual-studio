"""Planner: turns a structured request into a deterministic image plan.

The planner is the "brain" that decides *what* images a case needs. It is pure
and deterministic: identical input always yields identical plans.

Behaviour:
  * If the caller supplies ``images``, those are honoured verbatim (priority
    derived from image_type, overridable per image).
  * If ``images`` is empty, a default plan is synthesised: one ``main`` image
    carrying the primary selling point, one ``scene`` and one ``detail`` image,
    using the category's canvas presets.
"""

from __future__ import annotations

from visual_studio.domain.contracts import BatchRequest, ImageSpec
from visual_studio.domain.models import ImagePlan

# Priority by image type. Higher = more urgent. Extensible.
_TYPE_PRIORITY: dict[str, int] = {
    "main": 30,
    "scene": 20,
    "detail": 10,
}


class Planner:
    """Deterministic planner from structured product info to image plans."""

    def plan(self, request: BatchRequest) -> list[ImagePlan]:
        """Return the ordered list of :class:`ImagePlan` for a batch request."""
        if request.images:
            return [self._from_spec(spec, idx) for idx, spec in enumerate(request.images)]

        return self._default_plan(request)

    def _from_spec(self, spec: ImageSpec, idx: int) -> ImagePlan:
        priority = spec.priority
        if priority == 10 and spec.image_type in _TYPE_PRIORITY:
            # Default priority only if caller did not override.
            priority = _TYPE_PRIORITY[spec.image_type]
        return ImagePlan(
            image_type=spec.image_type,
            canvas=spec.canvas,
            selling_point=spec.selling_point,
            required_elements=list(spec.required_elements),
            forbidden_elements=list(spec.forbidden_elements),
            style_preset=spec.style_preset,
            priority=max(priority - idx, 1),
        )

    def _default_plan(self, request: BatchRequest) -> list[ImagePlan]:
        presets = request.category_spec.canvas_presets
        forbidden = list(request.category_spec.forbidden_terms)
        points = request.selling_points or ["generic"]

        plans: list[ImagePlan] = []

        # main: primary selling point.
        main_canvas = presets.get("main", "800x800")
        plans.append(
            ImagePlan(
                image_type="main",
                canvas=main_canvas,
                selling_point=points[0],
                required_elements=[],
                forbidden_elements=forbidden,
                style_preset="default",
                priority=_TYPE_PRIORITY["main"],
            )
        )

        # scene: secondary selling point (fallback to primary).
        scene_canvas = presets.get("scene", "1200x800")
        scene_point = points[1] if len(points) > 1 else points[0]
        plans.append(
            ImagePlan(
                image_type="scene",
                canvas=scene_canvas,
                selling_point=scene_point,
                required_elements=[],
                forbidden_elements=forbidden,
                style_preset="default",
                priority=_TYPE_PRIORITY["scene"],
            )
        )

        # detail: last selling point (fallback to primary).
        detail_canvas = presets.get("detail", "800x800")
        detail_point = points[-1]
        plans.append(
            ImagePlan(
                image_type="detail",
                canvas=detail_canvas,
                selling_point=detail_point,
                required_elements=[],
                forbidden_elements=forbidden,
                style_preset="default",
                priority=_TYPE_PRIORITY["detail"],
            )
        )

        return plans
