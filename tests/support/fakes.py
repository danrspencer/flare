"""Dict-backed stand-ins for the lookups grouping.py and scenes.py take."""

from typing import Optional

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
    observed_context_ids = observed_context_ids or {}
    latest_context_ids = latest_context_ids or {}
    latest_targets = latest_targets or {}
    observed_targets = observed_targets or {}
    latest_secondary_context_ids = latest_secondary_context_ids or {}
    observed_secondary_context_ids = observed_secondary_context_ids or {}

    def is_state(entity_id, value):
        return states.get(entity_id, {}).get("state") == value

    def state_attr(entity_id, attr):
        return states.get(entity_id, {}).get("attributes", {}).get(attr)

    def device_id(entity_id):
        return device_of.get(entity_id)

    def labels(target_id):
        return labels_of.get(target_id, [])

    def manufacturer_model(entity_id):
        return device_identity.get(device_of.get(entity_id), (None, None))

    def context_id(entity_id):
        return states.get(entity_id, {}).get("context_id")

    def observed_context_id(entity_id):
        return observed_context_ids.get(entity_id)

    def latest_context_id(entity_id):
        return latest_context_ids.get(entity_id)

    def latest_target(entity_id):
        return latest_targets.get(entity_id)

    def observed_target(entity_id):
        return observed_targets.get(entity_id)

    def latest_secondary_context_id(entity_id):
        return latest_secondary_context_ids.get(entity_id)

    def observed_secondary_context_id(entity_id):
        return observed_secondary_context_ids.get(entity_id)

    return EntityLookup(
        is_state=is_state,
        state_attr=state_attr,
        device_id=device_id,
        labels=labels,
        manufacturer_model=manufacturer_model,
        context_id=context_id,
        observed_context_id=observed_context_id,
        latest_context_id=latest_context_id,
        latest_target=latest_target,
        observed_target=observed_target,
        latest_secondary_context_id=latest_secondary_context_id,
        observed_secondary_context_id=observed_secondary_context_id,
    )


def make_scene_lookup(scenes: dict) -> SceneLookup:
    """scenes: {scene_entity_id: [covered_entity_id, ...]}; absent means
    the scene doesn't exist."""

    def exists(scene_entity_id):
        return scene_entity_id in scenes

    def covered_entities(scene_entity_id):
        return scenes.get(scene_entity_id, [])

    return SceneLookup(exists=exists, covered_entities=covered_entities)
