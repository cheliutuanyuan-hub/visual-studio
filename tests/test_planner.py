"""Tests for the deterministic planner."""

from visual_studio.domain.contracts import BatchRequest, CategorySpec, ImageSpec
from visual_studio.planner.planner import Planner


def _category(presets=None, forbidden=None):
    return CategorySpec(
        category="kitchen",
        canvas_presets=presets or {"main": "800x800", "scene": "1200x800", "detail": "800x800"},
        forbidden_terms=forbidden or ["最", "第一"],
    )


def test_default_plan_creates_main_scene_detail():
    req = BatchRequest(
        case_id="c1",
        platform="tmall",
        category_spec=_category(),
        selling_points=["便携", "USB充电"],
        images=[],
    )
    plans = Planner().plan(req)
    types = [p.image_type for p in plans]
    assert types == ["main", "scene", "detail"]


def test_default_plan_priorities_descending():
    req = BatchRequest(
        case_id="c1",
        platform="tmall",
        category_spec=_category(),
        selling_points=["a", "b"],
        images=[],
    )
    plans = Planner().plan(req)
    priorities = [p.priority for p in plans]
    assert priorities == sorted(priorities, reverse=True)
    assert priorities[0] == 30 and priorities[-1] == 10


def test_default_plan_uses_selling_points_and_forbidden_terms():
    req = BatchRequest(
        case_id="c1",
        platform="tmall",
        category_spec=_category(forbidden=["最"]),
        selling_points=["便携", "USB充电"],
        images=[],
    )
    plans = Planner().plan(req)
    # main carries the primary selling point.
    assert plans[0].selling_point == "便携"
    # forbidden term is propagated to every planned image.
    assert all("最" in p.forbidden_elements for p in plans)


def test_provided_images_are_honoured():
    req = BatchRequest(
        case_id="c1",
        platform="tmall",
        category_spec=_category(),
        selling_points=["便携"],
        images=[
            ImageSpec(
                image_type="main",
                canvas="800x800",
                selling_point="便携",
                required_elements=["榨汁杯", "水果"],
                forbidden_elements=["文字logo"],
                style_preset="default",
            )
        ],
    )
    plans = Planner().plan(req)
    assert len(plans) == 1
    assert plans[0].required_elements == ["榨汁杯", "水果"]
    assert plans[0].forbidden_elements == ["文字logo"]


def test_planner_is_deterministic():
    req = BatchRequest(
        case_id="c1",
        platform="tmall",
        category_spec=_category(),
        selling_points=["a", "b"],
        images=[],
    )
    a = Planner().plan(req)
    b = Planner().plan(req)
    assert [p.image_type for p in a] == [p.image_type for p in b]
    assert [p.priority for p in a] == [p.priority for p in b]
