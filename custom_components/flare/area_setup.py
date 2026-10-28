"""Sets up rooms in one go: for each area, an automation from the
blueprint and, optionally, a flare over that automation.

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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.util import slugify
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, load_yaml

from .blueprint_check import async_blueprint_path
from .const import (
    BLUEPRINT_LIGHTS_INPUT,
    CONF_AREA,
    CONF_AUTOMATION,
    CONF_ENTRY_TYPE,
    CONF_LIGHTS_INPUT,
    CONF_LIGHTS_INPUT_KIND,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SCHEDULES,
    SUBENTRY_TYPE_FLARE,
)
from .flares.automation import TARGET, automation_ref
from .flares.identity import is_flare_entry

_WRITE_LOCK = f"{DOMAIN}_automations_lock"

# The label on every automation setup creates, so they're easy to find.
LABEL_NAME = "FLARE"
LABEL_ICON = "flare:logo"
# One of the frontend's named label colours: warm, like the curve.
LABEL_COLOR = "amber"

# How much each area gets; each includes the ones before it.
AUTOMATION = "automation"
FLARE = "flare"
LEVELS = (AUTOMATION, FLARE)


class AutomationsNotLoaded(Exception):
    """configuration.yaml doesn't load automations.yaml."""


class AutomationsFileInvalid(Exception):
    """automations.yaml isn't a list of automations."""


@dataclass(frozen=True)
class Area:
    area_id: str
    name: str


@dataclass(frozen=True)
class SetupResult:
    automations: int
    flares: int


def areas_with_lights(hass: HomeAssistant) -> list[Area]:
    """Every area holding a light, by the entity's own area or its
    device's, sorted by name."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    area_ids = set()
    for entry in entity_registry.entities.values():
        if entry.domain != "light" or is_flare_entry(entry):
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


def areas_set_up(hass: HomeAssistant) -> set[str]:
    """Areas holding an automation with the FLARE label, which is where setup
    puts the automations it makes."""
    label = lr.async_get(hass).async_get_label_by_name(LABEL_NAME)
    if label is None:
        return set()
    return {
        entry.area_id
        for entry in er.async_get(hass).entities.values()
        if entry.domain == "automation" and label.label_id in entry.labels and entry.area_id
    }


async def async_set_up_areas(
    hass: HomeAssistant, schedule_for_area: dict[Area, str], level: str = FLARE
) -> SetupResult:
    """For each area an automation following the schedule subentry given
    for it and, depending on `level`, a flare over that. Raises
    AutomationsNotLoaded, leaving automations.yaml as it was, if the
    automations don't load."""
    flares_entry = _entry(hass, ENTRY_TYPE_FLARES)
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
                    BLUEPRINT_LIGHTS_INPUT: {"area_id": area.area_id},
                },
            },
        }
        for area, schedule_subentry_id in schedule_for_area.items()
    }
    entity_ids = await async_add_automations(hass, list(configs.values()))

    registry = er.async_get(hass)
    label = _flare_label(hass)
    for area, entity_id in zip(configs, entity_ids):
        entry = registry.async_get(entity_id)
        labels = (entry.labels if entry else set()) | {label}
        registry.async_update_entity(entity_id, area_id=area.area_id, labels=labels)
    if level == AUTOMATION:
        return SetupResult(automations=len(entity_ids), flares=0)
    for area, entity_id in zip(configs, entity_ids):
        hass.config_entries.async_add_subentry(flares_entry, room_flare(hass, flares_entry, entity_id, area.name))

    return SetupResult(automations=len(entity_ids), flares=len(entity_ids))


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
                CONF_AREA: registry_entry.area_id if registry_entry else None,
            }
        ),
    )


async def async_add_automations(hass: HomeAssistant, configs: list[dict[str, Any]]) -> list[str]:
    """Appends the automations to automations.yaml, reloads, and returns
    their entity_ids. Each is validated first, so nothing is written unless
    all of them are valid. Raises AutomationsFileInvalid, writing nothing,
    if the file can't be read as a list of automations."""
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
    try:
        items = load_yaml(path) if os.path.isfile(path) else None
    except HomeAssistantError as err:
        raise AutomationsFileInvalid from err
    if items is None:
        return []
    if not isinstance(items, list):
        raise AutomationsFileInvalid
    return items


def _restore(path: str, original: str | None) -> None:
    if original is None:
        os.remove(path)
    else:
        write_utf8_file_atomic(path, original)


def _flare_label(hass: HomeAssistant) -> str:
    """The FLARE label's id, creating the label the first time."""
    registry = lr.async_get(hass)
    label = registry.async_get_label_by_name(LABEL_NAME) or registry.async_create(
        LABEL_NAME, icon=LABEL_ICON, color=LABEL_COLOR
    )
    return label.label_id


def _entry(hass: HomeAssistant, entry_type: str, required: bool = True) -> ConfigEntry | None:
    entries = (e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == entry_type)
    return next(entries) if required else next(entries, None)


def _schedule_device(hass: HomeAssistant, subentry_id: str) -> str:
    entry = _entry(hass, ENTRY_TYPE_SCHEDULES)
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, subentry_id), entry.entry_id)
    if device is None:
        raise ValueError(f"No device for schedule {subentry_id}")
    return device.id
