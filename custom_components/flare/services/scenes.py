"""Which of your target entities a scene covers, so the scene can take
those and your default behaviour the rest. Nothing lighting-specific.
The blueprint keeps a Jinja copy, since a `condition:` can't call a
service."""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SceneLookup:
    exists: Callable[[str], bool]
    covered_entities: Callable[[str], list]


@dataclass
class SceneCoverage:
    scene_active: bool
    scene_valid: bool
    covered_entities: list = field(default_factory=list)
    uncovered_entities: list = field(default_factory=list)


def compute_scene_coverage(
    scene_entity_id: str,
    scope_entities: list,
    target_entities: list,
    lookup: SceneLookup,
) -> SceneCoverage:
    """A scene counts only if it exists and everything it covers is within
    scope_entities; otherwise it's treated as no scene at all."""
    if not lookup.exists(scene_entity_id):
        return SceneCoverage(
            scene_active=False,
            scene_valid=False,
            covered_entities=[],
            uncovered_entities=list(target_entities),
        )

    covered = list(lookup.covered_entities(scene_entity_id))
    valid = all(e in scope_entities for e in covered)

    if not valid:
        return SceneCoverage(
            scene_active=False,
            scene_valid=False,
            covered_entities=covered,
            uncovered_entities=list(target_entities),
        )

    return SceneCoverage(
        scene_active=True,
        scene_valid=True,
        covered_entities=covered,
        uncovered_entities=[e for e in target_entities if e not in covered],
    )
