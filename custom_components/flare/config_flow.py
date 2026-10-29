"""Config flow for FLARE.

Adding the integration creates the Schedules, Settings and Flares entries,
and after that the main flow sets up areas. Adding a schedule or flare is
a subentry flow (subentry_flows.py); the Settings entry's options are
options_flow.py."""

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
    Area,
    AutomationsFileInvalid,
    AutomationsNotLoaded,
    add_room_flares,
    areas_set_up,
    areas_with_lights,
    async_set_up_areas,
)
from .const import (
    CONF_AUTOMATION,
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_SETTINGS,
    FLARES_ENTRY_TITLE,
    SCHEDULES_ENTRY_TITLE,
    SETTINGS_ENTRY_TITLE,
    SUBENTRY_TYPE_FLARE,
    SUBENTRY_TYPE_SENSOR,
)
from .dashboard_reload import async_raise as async_raise_reload, reload_link
from .schedule.coordinator import schedule_instances
from .options_flow import FlareOptionsFlow
from .subentry_flows import FlareSubentryFlow, SensorSubentryFlow

# The one schedule's name, for the whole home.
DEFAULT_SCHEDULE_NAME = "Home"
# The schedules step's choice, and the names step's field.
LAYOUT = "layout"
PER_FLOOR = "per_floor"
HOME = "home"
CUSTOM = "custom"
NAMES = "names"
# The areas' section when no area has a floor, else the floorless areas'
# after a section per floor.
AREAS = "areas"
OTHER_AREAS = "other_areas"

_LOGGER = logging.getLogger(__name__)


class FlareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """The integration page's main button. The first time, it creates every
    entry and the schedules, then asks whether to set up areas; after
    that it sets up areas. Each area gets an automation from the blueprint,
    and then flares are offered for those rooms.

    The entries are created through SOURCE_IMPORT and the flow ends on an
    abort carrying a summary. Completing on an entry instead would show
    HA's "integration added" dialog, which prompts to rename and place
    every device that entry has, with no way to suppress it."""

    VERSION = 3
    # 2: FLARE 2.0, which removed zones (see async_migrate_entry).
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._new_schedules: list[str] = []
        self._first_setup = False
        # The automations this run created: entity_id -> its area's name.
        self._rooms: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if ENTRY_TYPE_SCHEDULES not in self._configured():
            return await self.async_step_schedules()
        return await self.async_step_areas()

    async def async_step_schedules(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """One schedule for the home, one per floor, or names of your own."""
        floors = _floor_names(self.hass)
        if user_input is not None:
            if user_input[LAYOUT] == CUSTOM:
                return await self.async_step_schedule_names()
            names = floors if user_input[LAYOUT] == PER_FLOOR else [DEFAULT_SCHEDULE_NAME]
            if errors := _name_errors(names):
                return await self.async_step_schedule_names(suggested=names, errors=errors)
            self._new_schedules = names
            return await self.async_step_automations()

        # One floor or none would make "per floor" the whole home under
        # another name. Its label lists the floors, so it isn't translated.
        options = [selector.SelectOptionDict(value=HOME, label=HOME)]
        if len(floors) > 1:
            options.append(selector.SelectOptionDict(value=PER_FLOOR, label=f"One per floor: {', '.join(floors)}"))
        options.append(selector.SelectOptionDict(value=CUSTOM, label=CUSTOM))
        return self.async_show_form(
            step_id="schedules",
            data_schema=vol.Schema(
                {
                    vol.Required(LAYOUT, default=HOME): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, translation_key=LAYOUT, mode=selector.SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    async def async_step_schedule_names(
        self,
        user_input: dict[str, Any] | None = None,
        *,
        suggested: list[str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> FlowResult:
        """A list of names, one schedule each."""
        if user_input is not None:
            names = [name.strip() for name in user_input.get(NAMES) or [] if name.strip()]
            if not (errors := _name_errors(names)):
                self._new_schedules = names
                return await self.async_step_automations()
            suggested = names
        if suggested is None:
            suggested = [DEFAULT_SCHEDULE_NAME]
        return self.async_show_form(
            step_id="schedule_names",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(NAMES): selector.TextSelector(selector.TextSelectorConfig(multiple=True))}),
                {NAMES: suggested},
            ),
            errors=errors or {},
        )

    async def async_step_automations(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Whether to set up room automations now. Someone whose own
        automations already drive their lights can skip it and move one
        room at a time."""
        if not areas_with_lights(self.hass):
            return await self.async_step_areas()
        return self.async_show_menu(step_id="automations", menu_options=["areas", "schedules_only"])

    async def async_step_schedules_only(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """The entries and schedules, with no automations yet."""
        await self._create_entries()
        placeholders = {"schedules": ", ".join(self._new_schedules), "reload": reload_link()}
        async_raise_reload(self.hass, placeholders["reload"])
        return self.async_abort(reason="schedules_set_up", description_placeholders=placeholders)

    async def async_step_areas(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Which areas to set up and, with more than one schedule, which
        schedule each follows. Every area with lights is listed; those
        not set up yet are picked."""
        self._first_setup = self._configured() != {ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_SETTINGS, ENTRY_TYPE_FLARES}
        schedules = self._schedule_choices()
        if not schedules:
            return self.async_abort(reason="no_schedules")
        areas = areas_with_lights(self.hass)
        if not areas and not self._first_setup:
            return self.async_abort(reason="no_areas")

        if user_input is None and areas:
            return self.async_show_form(
                step_id="areas",
                data_schema=_areas_schema(self.hass, areas, schedules, areas_set_up(self.hass)),
                description_placeholders={"schedules": ", ".join(name for _, name in schedules)},
            )

        chosen = _chosen(user_input or {}, areas, schedules)

        await self._create_entries()
        schedule_ids = self._schedule_ids()
        plan = {area: schedule_ids[key] for area, key in chosen.items()}
        try:
            self._rooms = await async_set_up_areas(self.hass, plan) if plan else {}
        except AutomationsNotLoaded:
            return self.async_abort(reason="automations_not_loaded")
        except AutomationsFileInvalid:
            return self.async_abort(reason="automations_invalid")
        except Exception:  # noqa: BLE001 - reported in the summary, details in the log
            _LOGGER.exception("Could not set up %s", ", ".join(area.name for area in plan))
            return self.async_abort(reason="setup_failed")

        if not self._rooms:
            return self._summary(flares=0)
        return await self.async_step_flares()

    async def async_step_flares(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """What flares are, and whether to add any for the rooms just set up."""
        return self.async_show_menu(step_id="flares", menu_options=["flare_rooms", "skip_flares"])

    async def async_step_flare_rooms(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """The rooms just set up, all ticked, as Add flare lists them. Each
        one picked gets a flare named after its area."""
        if user_input is not None:
            picked = {e: name for e, name in self._rooms.items() if e in user_input[CONF_AUTOMATION]}
            add_room_flares(self.hass, picked)
            return self._summary(flares=len(picked))
        options = [selector.SelectOptionDict(value=e, label=name) for e, name in self._rooms.items()]
        return self.async_show_form(
            step_id="flare_rooms",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTOMATION, default=list(self._rooms)): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def async_step_skip_flares(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self._summary(flares=0)

    def _summary(self, *, flares: int) -> FlowResult:
        """The flow's end: what was set up."""
        placeholders = {"automations": str(len(self._rooms)), "flares": str(flares)}
        if self._first_setup:
            placeholders["schedules"] = ", ".join(self._new_schedules)
            placeholders["reload"] = reload_link()
            async_raise_reload(self.hass, placeholders["reload"])
        return self.async_abort(
            reason="setup_complete" if self._first_setup else "areas_set_up", description_placeholders=placeholders
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
        if ENTRY_TYPE_SETTINGS not in configured:
            await self._import({CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS})
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
        return await self._create_settings_entry()

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

    async def _create_settings_entry(self) -> FlowResult:
        await self.async_set_unique_id(f"{DOMAIN}_{ENTRY_TYPE_SETTINGS}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=SETTINGS_ENTRY_TITLE, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS})

    async def _create_flares_entry(self) -> FlowResult:
        await self.async_set_unique_id(f"{DOMAIN}_{ENTRY_TYPE_FLARES}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=FLARES_ENTRY_TITLE, data={CONF_ENTRY_TYPE: ENTRY_TYPE_FLARES})

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SETTINGS:
            return {}
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES:
            return {SUBENTRY_TYPE_FLARE: FlareSubentryFlow}
        return {SUBENTRY_TYPE_SENSOR: SensorSubentryFlow}

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        """Only the Settings entry has options; nothing reads the Schedules entry's."""
        return config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SETTINGS

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        return FlareOptionsFlow()


def _areas_schema(
    hass: HomeAssistant, areas: list[Area], schedules: list[tuple[str, str]], set_up: set[str]
) -> vol.Schema:
    """The areas, a section per floor (lowest first, each named after its
    floor, which the dialog shows as its heading) with the floorless areas
    last. Each area is a dropdown of schedules,
    named after the area; an empty one isn't set up. An area already set up
    starts empty; the others start on the schedule named like their floor,
    else the first."""
    fields: dict = {}
    options = [selector.SelectOptionDict(value=key, label=name) for key, name in schedules]
    by_floor = {slugify(name): key for key, name in schedules}
    dropdown = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )
    by_section: dict[str, dict] = {floor: {} for floor in _floor_names(hass)}
    floorless = OTHER_AREAS if any(_floor_name(hass, a.area_id) for a in areas) else AREAS
    by_section[floorless] = {}
    for area in areas:
        floor = _floor_name(hass, area.area_id)
        # Suggested rather than a default, so an area cleared to nothing
        # stays cleared: that's how it's left out.
        suggested = None if area.area_id in set_up else by_floor.get(slugify(floor or ""), schedules[0][0])
        by_section[floor or floorless][vol.Optional(area.name, description={"suggested_value": suggested})] = dropdown
    for key, per_area in by_section.items():
        if per_area:
            fields[vol.Required(key)] = section(vol.Schema(per_area))
    return vol.Schema(fields)


def _floor_names(hass: HomeAssistant) -> list[str]:
    """Every floor's name, lowest first; floors without a level last."""
    floors = fr.async_get(hass).async_list_floors()
    return [f.name for f in sorted(floors, key=lambda f: (f.level is None, f.level or 0, f.name))]


def _name_errors(names: list[str]) -> dict[str, str]:
    """Schedule names need a letter or number, and to differ as entity IDs."""
    slugs = [slugify(name) for name in names]
    if not names:
        return {NAMES: "no_names"}
    if not all(any(c.isalnum() for c in name) for name in names):
        return {NAMES: "invalid_name"}
    if len(set(slugs)) < len(slugs):
        return {NAMES: "duplicate_name"}
    return {}


def _floor_name(hass: HomeAssistant, area_id: str) -> str | None:
    area = ar.async_get(hass).async_get_area(area_id)
    floor = fr.async_get(hass).async_get_floor(area.floor_id) if area and area.floor_id else None
    return floor.name if floor else None


def _chosen(user_input: dict[str, Any], areas: list[Area], schedules: list[tuple[str, str]]) -> dict[Area, str]:
    """Area -> schedule choice key, for every area set up, from whichever
    section it's in."""
    keys = {key for key, _ in schedules}
    picked = {name: value for part in user_input.values() if isinstance(part, dict) for name, value in part.items()}
    return {area: picked[area.name] for area in areas if picked.get(area.name) in keys}
