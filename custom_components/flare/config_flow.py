"""Config flow for FLARE.

Adding the integration creates the Schedules, Zones and Flares entries,
and after that the main flow sets up areas. Adding a schedule, zone or
flare is a subentry flow (subentry_flows.py); the Zones entry's options
are options_flow.py."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigSubentryFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .area_setup import (
    FLARE,
    LEVELS,
    Area,
    AutomationsFileInvalid,
    AutomationsNotLoaded,
    SetupResult,
    areas_with_lights,
    areas_with_zones,
    async_set_up_areas,
)
from .const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_ZONES,
    FLARES_ENTRY_TITLE,
    SCHEDULES_ENTRY_TITLE,
    SUBENTRY_TYPE_FLARE,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_ZONE,
    ZONES_ENTRY_TITLE,
)
from .schedule.coordinator import schedule_instances
from .options_flow import FlareOptionsFlow
from .subentry_flows import FlareSubentryFlow, SensorSubentryFlow, ZoneSubentryFlow

# The first schedule's suggested name, when there's only one.
DEFAULT_SCHEDULE_NAME = "Home"
MAX_SCHEDULES = 4
SKIP = "skip"
SET_UP = "set_up"
AREAS = "areas"

_LOGGER = logging.getLogger(__name__)


class FlareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """The integration page's main button. The first time, it creates every
    entry and the schedules; after that it sets up areas. Each area gets a
    zone, an automation from the blueprint and a flare.

    The entries are created through SOURCE_IMPORT and the flow ends on an
    abort carrying a summary. Completing on an entry instead would show
    HA's "integration added" dialog, which prompts to rename and place
    every device that entry has, with no way to suppress it."""

    VERSION = 3

    def __init__(self) -> None:
        self._schedule_count = 1
        self._new_schedules: list[str] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if ENTRY_TYPE_SCHEDULES not in self._configured():
            return await self.async_step_schedules()
        return await self.async_step_areas()

    async def async_step_schedules(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """How many schedules: one for the house, or one per floor."""
        if user_input is not None:
            self._schedule_count = int(user_input["count"])
            return await self.async_step_schedule_names()
        return self.async_show_form(
            step_id="schedules",
            data_schema=vol.Schema(
                {
                    vol.Required("count", default=1): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=MAX_SCHEDULES, step=1, mode=selector.NumberSelectorMode.BOX)
                    )
                }
            ),
        )

    async def async_step_schedule_names(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        keys = [f"schedule_{n}" for n in range(1, self._schedule_count + 1)]
        errors: dict[str, str] = {}
        if user_input is not None:
            names = [user_input.get(key, "").strip() for key in keys]
            slugs = [slugify(name) for name in names]
            for key, name, slug in zip(keys, names, slugs):
                if not any(c.isalnum() for c in name):
                    errors[key] = "invalid_name"
                elif slugs.count(slug) > 1:
                    errors[key] = "duplicate_name"
            if not errors:
                self._new_schedules = names
                return await self.async_step_areas()
        suggested = user_input or ({"schedule_1": DEFAULT_SCHEDULE_NAME} if len(keys) == 1 else {})
        return self.async_show_form(
            step_id="schedule_names",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(key): selector.TextSelector() for key in keys}), suggested
            ),
            errors=errors,
        )

    async def async_step_areas(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Which areas to set up and, with more than one schedule, which
        schedule each follows. Every area with lights is listed; those
        without a zone yet are picked."""
        first_setup = self._configured() != {ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_ZONES, ENTRY_TYPE_FLARES}
        schedules = self._schedule_choices()
        if not schedules:
            return self.async_abort(reason="no_schedules")
        areas = areas_with_lights(self.hass)
        if not areas and not first_setup:
            return self.async_abort(reason="no_areas")

        if user_input is None and areas:
            return self.async_show_form(
                step_id="areas",
                data_schema=_areas_schema(self.hass, areas, schedules, areas_with_zones(self.hass)),
                description_placeholders={"schedules": ", ".join(name for _, name in schedules)},
            )

        chosen = _chosen((user_input or {}).get(AREAS) or {}, areas, schedules)

        await self._create_entries()
        schedule_ids = self._schedule_ids()
        plan = {area: schedule_ids[key] for area, key in chosen.items()}
        try:
            level = (user_input or {}).get(SET_UP, FLARE)
            result = await async_set_up_areas(self.hass, plan, level) if plan else SetupResult(0, 0, 0)
        except AutomationsNotLoaded:
            return self.async_abort(reason="automations_not_loaded")
        except AutomationsFileInvalid:
            return self.async_abort(reason="automations_invalid")
        except Exception:  # noqa: BLE001 - reported in the summary, details in the log
            _LOGGER.exception("Could not set up %s", ", ".join(area.name for area in plan))
            return self.async_abort(reason="setup_failed")

        counts = {"zones": result.zones, "automations": result.automations, "flares": result.flares}
        placeholders = {key: str(count) for key, count in counts.items()}
        if first_setup:
            placeholders["schedules"] = ", ".join(self._new_schedules)
        return self.async_abort(
            reason="setup_complete" if first_setup else "areas_set_up", description_placeholders=placeholders
        )

    def _configured(self) -> set[str]:
        return {entry.data.get(CONF_ENTRY_TYPE) for entry in self._async_current_entries()}

    def _schedule_choices(self) -> list[tuple[str, str]]:
        """(key, name) per schedule: an index for one being created now, its
        subentry id for one that exists."""
        if self._new_schedules:
            return [(f"schedule_{n}", name) for n, name in enumerate(self._new_schedules, 1)]
        entry = self._entry(ENTRY_TYPE_SCHEDULES)
        return [(i.subentry_id, i.title) for i in schedule_instances(entry)] if entry else []

    def _schedule_ids(self) -> dict[str, str]:
        """Choice key -> subentry id, once the schedules exist."""
        instances = schedule_instances(self._entry(ENTRY_TYPE_SCHEDULES))
        by_name = {i.title: i.subentry_id for i in instances}
        ids = {i.subentry_id: i.subentry_id for i in instances}
        ids.update({f"schedule_{n}": by_name[name] for n, name in enumerate(self._new_schedules, 1)})
        return ids

    def _entry(self, entry_type: str) -> ConfigEntry | None:
        return next((e for e in self._async_current_entries() if e.data.get(CONF_ENTRY_TYPE) == entry_type), None)

    async def _create_entries(self) -> None:
        """Creates whichever entries are missing."""
        configured = self._configured()
        if ENTRY_TYPE_SCHEDULES not in configured:
            await self._import({CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES, "schedules": self._new_schedules})
        if ENTRY_TYPE_ZONES not in configured:
            await self._import({CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES})
        if ENTRY_TYPE_FLARES not in configured:
            await self._import({CONF_ENTRY_TYPE: ENTRY_TYPE_FLARES})

    async def _import(self, data: dict[str, Any]) -> None:
        await self.hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=data)

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Creates one entry without a visible flow (see the class docstring)."""
        if import_data[CONF_ENTRY_TYPE] == ENTRY_TYPE_SCHEDULES:
            return await self._create_schedules_entry(import_data["schedules"])
        if import_data[CONF_ENTRY_TYPE] == ENTRY_TYPE_FLARES:
            return await self._create_flares_entry()
        return await self._create_zones_entry()

    async def _create_schedules_entry(self, schedules: list[str]) -> FlowResult:
        await self.async_set_unique_id(f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=SCHEDULES_ENTRY_TITLE,
            data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
            subentries=[
                {"subentry_type": SUBENTRY_TYPE_SENSOR, "title": name, "unique_id": slugify(name), "data": {}}
                for name in schedules
            ],
        )

    async def _create_zones_entry(self) -> FlowResult:
        await self.async_set_unique_id(f"{DOMAIN}_{ENTRY_TYPE_ZONES}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=ZONES_ENTRY_TITLE, data={CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES})

    async def _create_flares_entry(self) -> FlowResult:
        await self.async_set_unique_id(f"{DOMAIN}_{ENTRY_TYPE_FLARES}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=FLARES_ENTRY_TITLE, data={CONF_ENTRY_TYPE: ENTRY_TYPE_FLARES})

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ZONES:
            return {SUBENTRY_TYPE_ZONE: ZoneSubentryFlow}
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES:
            return {SUBENTRY_TYPE_FLARE: FlareSubentryFlow}
        return {SUBENTRY_TYPE_SENSOR: SensorSubentryFlow}

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        """Only the Zones entry has options; nothing reads the Schedules entry's."""
        return config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ZONES

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        return FlareOptionsFlow()


def _areas_schema(
    hass: HomeAssistant, areas: list[Area], schedules: list[tuple[str, str]], zoned: set[str]
) -> vol.Schema:
    """What to set up, then an Areas section with a dropdown per area -
    Don't set up, or a schedule - each field named after its area, which
    the dialog shows as its label. The section sets the areas apart from
    the choice above them. An area with a zone starts as Don't set up; the
    others start on the schedule named like their floor, else the first."""
    fields: dict = {
        vol.Required(SET_UP, default=FLARE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(LEVELS), translation_key="set_up", mode=selector.SelectSelectorMode.DROPDOWN
            )
        )
    }
    options = [selector.SelectOptionDict(value=SKIP, label="-- Don't set up --")]
    options += [selector.SelectOptionDict(value=key, label=name) for key, name in schedules]
    by_floor = {slugify(name): key for key, name in schedules}
    dropdown = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, translation_key="area_schedule", mode=selector.SelectSelectorMode.DROPDOWN
        )
    )
    per_area: dict = {}
    for area in areas:
        floor = _floor_name(hass, area.area_id)
        default = SKIP if area.area_id in zoned else by_floor.get(slugify(floor or ""), schedules[0][0])
        per_area[vol.Required(area.name, default=default)] = dropdown
    fields[vol.Required(AREAS)] = section(vol.Schema(per_area))
    return vol.Schema(fields)


def _floor_name(hass: HomeAssistant, area_id: str) -> str | None:
    area = ar.async_get(hass).async_get_area(area_id)
    floor = fr.async_get(hass).async_get_floor(area.floor_id) if area and area.floor_id else None
    return floor.name if floor else None


def _chosen(user_input: dict[str, Any], areas: list[Area], schedules: list[tuple[str, str]]) -> dict[Area, str]:
    """Area -> schedule choice key, for every area set up."""
    keys = {key for key, _ in schedules}
    return {area: user_input[area.name] for area in areas if user_input.get(area.name) in keys}
