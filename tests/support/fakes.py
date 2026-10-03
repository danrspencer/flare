"""Dict-backed stand-ins for the lookups grouping.py and scenes.py take."""

from typing import Optional

from homeassistant.core import Context, State

from custom_components.flare.services.grouping import EntityLookup
from custom_components.flare.services.scenes import SceneLookup


def make_lookup(
    states: dict,
    device_of: Optional[dict] = None,
    labels_of: Optional[dict] = None,
    device_identity: Optional[dict] = None,
    observed_context_ids: Optional[dict] = None,
    latest_context_ids: Optional[dict] = None,
    latest_targets: Optional[dict] = None,
    observed_targets: Optional[dict] = None,
    latest_secondary_context_ids: Optional[dict] = None,
    observed_secondary_context_ids: Optional[dict] = None,
) -> EntityLookup:
    """
    states:    {entity_id: {"state": ..., "attributes": {...}, "context_id": ...}}
    device_of: {entity_id: device_id}
    labels_of: {entity_id or device_id: [label, ...]}
    device_identity: {device_id: (manufacturer, model)}
    observed_/latest_context_ids, _targets, _secondary_context_ids:
               {entity_id: value} for each claim field; absent means none.
    """
    device_of = device_of or {}
    labels_of = labels_of or {}
    device_identity = device_identity or {}
    claim_fields = {
        "observed": (observed_context_ids, observed_secondary_context_ids, observed_targets),
        "latest": (latest_context_ids, latest_secondary_context_ids, latest_targets),
    }

    def state(entity_id):
        fake = states.get(entity_id)
        if fake is None or "state" not in fake:
            return None
        return State(
            entity_id,
            fake["state"],
            fake.get("attributes", {}),
            context=Context(id=fake.get("context_id")),
        )

    def claim(entity_id, context_ids, secondary_context_ids, targets):
        context_id = (context_ids or {}).get(entity_id)
        if context_id is None:
            return None
        return {
            "context_id": context_id,
            "secondary_context_id": (secondary_context_ids or {}).get(entity_id),
            "target": (targets or {}).get(entity_id),
        }

    def claims(entity_id):
        record = {name: claim(entity_id, *fields) for name, fields in claim_fields.items()}
        return record if any(record.values()) else None

    return EntityLookup(
        state=state,
        device_id=device_of.get,
        labels=lambda target_id: labels_of.get(target_id, []),
        manufacturer_model=lambda entity_id: device_identity.get(device_of.get(entity_id), (None, None)),
        claims=claims,
    )


def make_scene_lookup(scenes: dict) -> SceneLookup:
    """scenes: {scene_entity_id: [covered_entity_id, ...]}; absent means
    the scene doesn't exist."""

    def exists(scene_entity_id):
        return scene_entity_id in scenes

    def covered_entities(scene_entity_id):
        return scenes.get(scene_entity_id, [])

    return SceneLookup(exists=exists, covered_entities=covered_entities)
