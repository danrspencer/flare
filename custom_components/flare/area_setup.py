"""Sets up rooms in one go: for each area, a zone, and optionally an
automation from the blueprint and a flare over that automation.

The automation is written to automations.yaml the way HA's automation
editor writes it (`components/config/automation.py`): read the file, add
the item, write it back atomically, reload. There is no public API for
it. If the reload doesn't load them, configuration.yaml doesn't include
the file, and it's put back as it was."""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.config import AUTOMATION_CONFIG_PATH
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, load_yaml

from .blueprint_check import async_blueprint_path, automations_using_our_blueprint
from .const import (
    BLUEPRINT_LIGHTS_INPUT,
    BLUEPRINT_ZONE_INPUT,
    CONF_AREA,
    CONF_AUTOMATION,
    CONF_ENTRY_TYPE,
    CONF_LIGHTS_INPUT,
    CONF_LIGHTS_INPUT_KIND,
    CONF_ZONE_INPUT,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_ZONES,
    SUBENTRY_TYPE_FLARE,
    SUBENTRY_TYPE_ZONE,
)
from .flares.automation import TARGET, automation_ref, blueprint_inputs
from .zone.instance import zone_instances

_WRITE_LOCK = f"{DOMAIN}_automations_lock"

# How much each area gets; each includes the ones before it.
ZONE = "zone"
AUTOMATION = "automation"
FLARE = "flare"
LEVELS = (ZONE, AUTOMATION, FLARE)


class AutomationsNotLoaded(Exception):
    """configuration.yaml doesn't load automations.yaml."""


@dataclass(frozen=True)
class Area:
    area_id: str
    name: str


@dataclass(frozen=True)
class SetupResult:
    zones: int
    automations: int
    flares: int


def areas_with_lights(hass: HomeAssistant) -> list[Area]:
    """Every area holding a light, by the entity's own area or its
    device's, sorted by name."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    area_ids = set()
    for entry in entity_registry.entities.values():
        if entry.domain != "light" or entry.platform == DOMAIN:
            continue
        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = device_registry.async_get(entry.device_id)
            area_id = device.area_id if device else None
        if area_id:
            area_ids.add(area_id)
    area_registry = ar.async_get(hass)
    areas = [Area(a, area.name) for a in area_ids if (area := area_registry.async_get_area(a)) is not None]
    return sorted(areas, key=lambda area: area.name)


async def async_areas_set_up(hass: HomeAssistant) -> set[str]:
    """Areas a FLARE automation already targets by area."""
    covered: set[str] = set()
    for entity_id in await automations_using_our_blueprint(hass):
        target = (blueprint_inputs(hass, entity_id) or {}).get(BLUEPRINT_LIGHTS_INPUT) or {}
        area_ids = target.get("area_id", []) if isinstance(target, dict) else []
        covered.update([area_ids] if isinstance(area_ids, str) else area_ids)
    return covered


async def async_set_up_areas(
    hass: HomeAssistant, schedule_for_area: dict[Area, str], level: str = FLARE
) -> SetupResult:
    """For each area a zone and, depending on `level`, an automation
    following the schedule subentry given for it, and a flare over that.
    Zones that already exist by name are reused. Raises
    AutomationsNotLoaded, leaving automations.yaml as it was, if the
    automations don't load."""
    zones_entry = _entry(hass, ENTRY_TYPE_ZONES)
    flares_entry = _entry(hass, ENTRY_TYPE_FLARES)
    zones_before = len(zone_instances(zones_entry))
    zone_devices = {area: _zone_device(hass, zones_entry, area.name) for area in schedule_for_area}
    zones = len(zone_instances(zones_entry)) - zones_before
    if level == ZONE:
        return SetupResult(zones=zones, automations=0, flares=0)

    path = await async_blueprint_path(hass)
    configs = {
        area: {
            "id": uuid.uuid4().hex,
            "alias": f"{area.name} Lighting",
            "description": "Created by FLARE.",
            "use_blueprint": {
                "path": path,
                "input": {
                    "schedule": _schedule_device(hass, schedule_subentry_id),
                    "zone": zone_devices[area],
                    BLUEPRINT_LIGHTS_INPUT: {"area_id": area.area_id},
                },
            },
        }
        for area, schedule_subentry_id in schedule_for_area.items()
    }
    entity_ids = await async_add_automations(hass, list(configs.values()))

    registry = er.async_get(hass)
    for area, entity_id in zip(configs, entity_ids):
        registry.async_update_entity(entity_id, area_id=area.area_id)
    if level == AUTOMATION:
        return SetupResult(zones=zones, automations=len(entity_ids), flares=0)
    for area, entity_id in zip(configs, entity_ids):
        hass.config_entries.async_add_subentry(flares_entry, room_flare(hass, flares_entry, entity_id, area.name))

    return SetupResult(zones=zones, automations=len(entity_ids), flares=len(entity_ids))


def room_flare(hass: HomeAssistant, entry: ConfigEntry, entity_id: str, name: str) -> ConfigSubentry:
    """A flare over a FLARE room automation, in its area. A taken name gets a
    number."""
    taken = {slugify(subentry.title) for subentry in entry.subentries.values()}
    title, n = name, 2
    while slugify(title) in taken:
        title, n = f"{name} {n}", n + 1
    registry_entry = er.async_get(hass).async_get(entity_id)
    return ConfigSubentry(
        subentry_type=SUBENTRY_TYPE_FLARE,
        title=title,
        unique_id=slugify(title) or None,
        data=MappingProxyType(
            {
                CONF_AUTOMATION: automation_ref(hass, entity_id),
                CONF_LIGHTS_INPUT: BLUEPRINT_LIGHTS_INPUT,
                CONF_LIGHTS_INPUT_KIND: TARGET,
                CONF_ZONE_INPUT: BLUEPRINT_ZONE_INPUT,
                CONF_AREA: registry_entry.area_id if registry_entry else None,
            }
        ),
    )


async def async_add_automations(hass: HomeAssistant, configs: list[dict[str, Any]]) -> list[str]:
    """Appends the automations to automations.yaml, reloads, and returns
    their entity_ids. Each is validated first, so nothing is written unless
    all of them are valid."""
    for config in configs:
        await async_validate_config_item(hass, config["id"], config)

    path = hass.config.path(AUTOMATION_CONFIG_PATH)
    lock = hass.data.setdefault(_WRITE_LOCK, asyncio.Lock())
    async with lock:
        original = await hass.async_add_executor_job(_read_text, path)
        current = await hass.async_add_executor_job(_read_items, path)
        await hass.async_add_executor_job(write_utf8_file_atomic, path, dump([*current, *configs]))
        await hass.services.async_call("automation", "reload", blocking=True)

        registry = er.async_get(hass)
        entity_ids = [registry.async_get_entity_id("automation", "automation", c["id"]) for c in configs]
        if None in entity_ids:
            await hass.async_add_executor_job(_restore, path, original)
            await hass.services.async_call("automation", "reload", blocking=True)
            raise AutomationsNotLoaded
    return entity_ids


def _read_text(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as file:
        return file.read()


def _read_items(path: str) -> list:
    items = load_yaml(path) if os.path.isfile(path) else None
    if items is None:
        return []
    if not isinstance(items, list):
        raise AutomationsNotLoaded
    return items


def _restore(path: str, original: str | None) -> None:
    if original is None:
        os.remove(path)
    else:
        write_utf8_file_atomic(path, original)


def _entry(hass: HomeAssistant, entry_type: str) -> ConfigEntry:
    return next(e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == entry_type)


def _zone_device(hass: HomeAssistant, entry: ConfigEntry, name: str) -> str:
    """The device of the zone called `name`, adding the zone if there isn't
    one. The device is created here rather than on the entry's reload, so
    its id is known now; the reload finds it by its identifiers."""
    slug = slugify(name)
    zone = next((z for z in zone_instances(entry) if slugify(z.title) == slug), None)
    if zone is None:
        subentry = ConfigSubentry(
            subentry_type=SUBENTRY_TYPE_ZONE, title=name, unique_id=slug or None, data=MappingProxyType({})
        )
        hass.config_entries.async_add_subentry(entry, subentry)
        zone = next(z for z in zone_instances(entry) if z.subentry_id == subentry.subentry_id)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, config_subentry_id=zone.subentry_id, **zone.device_info
    )
    return device.id


def _schedule_device(hass: HomeAssistant, subentry_id: str) -> str:
    entry = _entry(hass, ENTRY_TYPE_SCHEDULES)
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, subentry_id), entry.entry_id)
    if device is None:
        raise ValueError(f"No device for schedule {subentry_id}")
    return device.id
