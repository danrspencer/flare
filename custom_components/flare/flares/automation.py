"""Reads a flare's automation: which lights it controls and which zone it
records them in.

A blueprint automation's inputs are only kept on the automation entity's
private `_blueprint_inputs` (its `raw_config` is the substituted config),
so this is the one place that reads them.
`tests/checks/test_ha_contracts.py` pins the shape."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.automation import DATA_COMPONENT, blueprint_in_automation
from homeassistant.components.automation.helpers import async_get_blueprints
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import (
    DOMAIN,
    CONF_AUTOMATION,
    CONF_LIGHTS_INPUT,
    CONF_LIGHTS_INPUT_KIND,
    CONF_LIGHTS_TARGET,
    CONF_ZONE_INPUT,
)

TARGET = "target"

# A blueprint input's selector, and the target key its value goes under.
# A target selector's value is already a whole target.
_LIGHTS_SELECTORS = {
    "target": TARGET,
    "area": "area_id",
    "device": "device_id",
    "entity": "entity_id",
    "floor": "floor_id",
    "label": "label_id",
}


def automation_ref(hass: HomeAssistant, entity_id: str) -> str:
    """What a flare stores: the registry id, which survives a rename, or the
    entity_id for an automation without one (YAML with no `id`)."""
    entry = er.async_get(hass).async_get(entity_id)
    return entry.id if entry else entity_id


def automation_entity_id(hass: HomeAssistant, config: Mapping[str, Any]) -> str | None:
    """The flare's automation's current entity_id."""
    return er.async_resolve_entity_id(er.async_get(hass), config[CONF_AUTOMATION])


def blueprint_inputs(hass: HomeAssistant, entity_id: str) -> dict[str, Any] | None:
    """The inputs an automation was given, or None if it isn't loaded or
    isn't from a blueprint."""
    component = hass.data.get(DATA_COMPONENT)
    entity = component.get_entity(entity_id) if component else None
    raw = getattr(entity, "_blueprint_inputs", None)
    if not raw:
        return None
    return dict(raw.get("use_blueprint", {}).get("input") or {})


def automation_exists(hass: HomeAssistant, entity_id: str | None) -> bool:
    component = hass.data.get(DATA_COMPONENT)
    return bool(entity_id and component and component.get_entity(entity_id))


def lights_target(hass: HomeAssistant, config: Mapping[str, Any]) -> dict[str, Any] | None:
    """The flare's lights, as a target. None when the automation, or the
    input naming them, is missing."""
    if config.get(CONF_LIGHTS_TARGET):
        return dict(config[CONF_LIGHTS_TARGET])
    entity_id = automation_entity_id(hass, config)
    inputs = blueprint_inputs(hass, entity_id) if entity_id else None
    if inputs is None:
        return None
    value = inputs.get(config.get(CONF_LIGHTS_INPUT))
    if not value:
        return None
    kind = config.get(CONF_LIGHTS_INPUT_KIND, TARGET)
    if kind == TARGET:
        return dict(value) if isinstance(value, Mapping) else None
    return {kind: value}


def zone_device_id(hass: HomeAssistant, config: Mapping[str, Any]) -> str | None:
    """The zone the flare's turn-off records in, or None for untracked."""
    name = config.get(CONF_ZONE_INPUT)
    entity_id = automation_entity_id(hass, config)
    if not name or not entity_id:
        return None
    value = (blueprint_inputs(hass, entity_id) or {}).get(name)
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) and value else None


async def async_automation_blueprint(hass: HomeAssistant, entity_id: str) -> Blueprint | None:
    """The blueprint an automation is built from, if any."""
    path = blueprint_in_automation(hass, entity_id)
    if path is None:
        return None
    try:
        return await async_get_blueprints(hass).async_get_blueprint(path)
    except Exception:  # noqa: BLE001 - a broken blueprint just offers no inputs
        return None


def _filters(config: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """A selector's filters, from either its `filter` list or its own keys."""
    config = config or {}
    filters = config.get("filter")
    if filters is None:
        return [config]
    return list(filters) if isinstance(filters, list) else [filters]


def _allows_lights(entity_config: Mapping[str, Any] | list | None) -> bool:
    """True for an entity filter naming the light domain. One naming no domain
    at all could hold anything, so it doesn't count."""
    configs = entity_config if isinstance(entity_config, list) else _filters(entity_config)
    for config in configs:
        domains = config.get("domain")
        if domains == "light" or (isinstance(domains, list) and "light" in domains):
            return True
    return False


def _flare_device_models(device_config: Mapping[str, Any] | None) -> set[str | None]:
    """The models a device selector is limited to among FLARE's own devices,
    or an empty set if it isn't limited to them."""
    return {f.get("model") for f in _filters(device_config) if f.get("integration") == DOMAIN}


def lights_input_kinds(blueprint: Blueprint) -> dict[str, str]:
    """Each input that can name lights, and the target key its value is."""
    kinds = {}
    for name, spec in blueprint.inputs.items():
        selector = (spec or {}).get("selector") or {}
        if "entity" in selector and not _allows_lights(selector["entity"]):
            continue
        if "device" in selector and _flare_device_models(selector["device"]):
            continue  # a FLARE schedule or zone, never a light
        for selector_type, kind in _LIGHTS_SELECTORS.items():
            if selector_type in selector:
                kinds[name] = kind
                break
    return kinds


def zone_inputs(blueprint: Blueprint) -> list[str]:
    """Each input that can pick a FLARE zone: one limited to zones, or failing
    that, any device input not limited to something else."""
    devices = {
        name: _flare_device_models(((spec or {}).get("selector") or {}).get("device"))
        for name, spec in blueprint.inputs.items()
        if "device" in ((spec or {}).get("selector") or {})
    }
    zones = [name for name, models in devices.items() if "Zone" in models]
    return zones or [name for name, models in devices.items() if not models]
