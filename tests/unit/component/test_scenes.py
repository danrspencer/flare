from custom_components.flare.services.scenes import compute_scene_coverage
from tests.support.fakes import make_scene_lookup


def test_nonexistent_scene_covers_nothing():
    lookup = make_scene_lookup({})
    result = compute_scene_coverage(
        "scene.missing", scope_entities=["light.a"], target_entities=["light.a", "light.b"], lookup=lookup
    )
    assert result.scene_active is False
    assert result.scene_valid is False
    assert result.uncovered_entities == ["light.a", "light.b"]


def test_scene_within_scope_is_active_and_covers_its_entities():
    lookup = make_scene_lookup({"scene.night": ["light.a"]})
    result = compute_scene_coverage(
        "scene.night", scope_entities=["light.a", "light.b"], target_entities=["light.a", "light.b"], lookup=lookup
    )
    assert result.scene_active is True
    assert result.scene_valid is True
    assert result.covered_entities == ["light.a"]
    assert result.uncovered_entities == ["light.b"]


def test_scene_reaching_outside_scope_is_treated_as_no_scene():
    lookup = make_scene_lookup({"scene.night": ["light.a", "light.c"]})
    result = compute_scene_coverage(
        "scene.night", scope_entities=["light.a", "light.b"], target_entities=["light.a", "light.b"], lookup=lookup
    )
    assert result.scene_active is False
    assert result.scene_valid is False
    assert result.uncovered_entities == ["light.a", "light.b"]


def test_scene_covering_nothing_within_scope_is_still_valid_and_active():
    lookup = make_scene_lookup({"scene.night": []})
    result = compute_scene_coverage(
        "scene.night", scope_entities=["light.a"], target_entities=["light.a", "light.b"], lookup=lookup
    )
    assert result.scene_active is True
    assert result.scene_valid is True
    assert result.covered_entities == []
    assert result.uncovered_entities == ["light.a", "light.b"]


def test_scene_covering_everything_leaves_nothing_uncovered():
    lookup = make_scene_lookup({"scene.night": ["light.a", "light.b"]})
    result = compute_scene_coverage(
        "scene.night", scope_entities=["light.a", "light.b"], target_entities=["light.a", "light.b"], lookup=lookup
    )
    assert result.scene_active is True
    assert result.uncovered_entities == []
