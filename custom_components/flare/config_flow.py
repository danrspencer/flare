"""Config flow for FLARE.

Adding the integration creates the Schedules, Zones and Flares entries.
Schedule sensors are "sensor" subentries, added and named by the user;
their times and curve values are entities on the sensor's device."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    ConfigEntry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.util import slugify

from .area_setup import (
    FLARE,
    LEVELS,
    Area,
    AutomationsNotLoaded,
    SetupResult,
    areas_with_lights,
    async_areas_set_up,
    async_set_up_areas,
    room_flare,
)
from .blueprint_check import automations_using_our_blueprint
from .const import (
    BLUEPRINT_LIGHTS_INPUT,
    CONF_AREA,
    CONF_AUTOMATION,
    CONF_ENTRY_TYPE,
    CONF_LIGHTS_INPUT,
    CONF_LIGHTS_INPUT_KIND,
    CONF_LIGHTS_TARGET,
    CONF_ZONE_INPUT,
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TICK_GAP,
    CONF_TICK_INTERVAL,
    CONF_TWO_STEP_MODELS,
    DEFAULT_MIN_BRIGHTNESS_CHANGE,
    DEFAULT_MIN_COLOR_TEMP_CHANGE,
    DEFAULT_TICK_GAP,
    DEFAULT_TICK_INTERVAL,
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
from .flares.automation import (
    TARGET,
    async_automation_blueprint,
    automation_entity_id,
    automation_ref,
    blueprint_inputs,
    lights_input_kinds,
    zone_inputs,
)
from .schedule.coordinator import schedule_instances
from .schedule.transfer import ScheduleError, dump, parse
from .services.schedules import async_apply_schedule, read_schedule, schedule_instance_for
from .services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS

SUBENTRY_FIELDS = {vol.Required("name"): selector.TextSelector()}

# The first schedule's suggested name, when there's only one.
DEFAULT_SCHEDULE_NAME = "Home"
MAX_SCHEDULES = 4
SKIP = "skip"
SET_UP = "set_up"

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
        schedule each follows. On first setup every area with lights is
        picked; afterwards, none are, and areas already set up aren't offered."""
        first_setup = self._configured() != {ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_ZONES, ENTRY_TYPE_FLARES}
        schedules = self._schedule_choices()
        if not schedules:
            return self.async_abort(reason="no_schedules")
        set_up = await async_areas_set_up(self.hass)
        areas = [area for area in areas_with_lights(self.hass) if area.area_id not in set_up]
        if not areas and not first_setup:
            return self.async_abort(reason="every_area_set_up")

        if user_input is None and areas:
            return self.async_show_form(
                step_id="areas",
                data_schema=_areas_schema(areas, schedules, first_setup),
                description_placeholders={"schedules": ", ".join(name for _, name in schedules)},
            )

        chosen = _chosen(user_input or {}, areas, schedules)
        created = await self._create_entries()
        schedule_ids = self._schedule_ids()
        plan = {area: schedule_ids[key] for area, key in chosen.items()}
        try:
            level = (user_input or {}).get(SET_UP, FLARE)
            result = await async_set_up_areas(self.hass, plan, level) if plan else SetupResult(0, 0, 0)
        except AutomationsNotLoaded:
            return self.async_abort(reason="automations_not_loaded")
        except Exception:  # noqa: BLE001 - reported in the summary, details in the log
            _LOGGER.exception("Could not set up %s", ", ".join(area.name for area in plan))
            return self.async_abort(reason="setup_failed")

        summary = [*created, *_counts(result)]
        return self.async_abort(
            reason="setup_complete" if first_setup else "areas_set_up",
            description_placeholders={"created": _join(summary) if summary else "nothing new"},
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

    async def _create_entries(self) -> list[str]:
        """Creates whichever entries are missing; returns what to report."""
        configured = self._configured()
        created = []
        if ENTRY_TYPE_SCHEDULES not in configured:
            await self._import({CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES, "schedules": self._new_schedules})
            names = self._new_schedules
            created.append(f"a schedule called {names[0]}" if len(names) == 1 else f"schedules called {_join(names)}")
        if ENTRY_TYPE_ZONES not in configured:
            await self._import({CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES})
        if ENTRY_TYPE_FLARES not in configured:
            await self._import({CONF_ENTRY_TYPE: ENTRY_TYPE_FLARES})
        return created

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


def _areas_schema(areas: list[Area], schedules: list[tuple[str, str]], first_setup: bool) -> vol.Schema:
    """What to set up, then the areas. With one schedule, a tick per area.
    With more, a schedule per area, each field named after its area, which
    the dialog shows as its label."""
    fields: dict = {
        vol.Required(SET_UP, default=FLARE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(LEVELS), translation_key="set_up", mode=selector.SelectSelectorMode.LIST
            )
        )
    }
    if len(schedules) == 1:
        options = [selector.SelectOptionDict(value=area.area_id, label=area.name) for area in areas]
        default = [area.area_id for area in areas] if first_setup else []
        fields[vol.Optional("areas", default=default)] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.LIST)
        )
        return vol.Schema(fields)
    options = [selector.SelectOptionDict(value=key, label=name) for key, name in schedules]
    options.append(selector.SelectOptionDict(value=SKIP, label="Don't set up"))
    default = schedules[0][0] if first_setup else SKIP
    for area in areas:
        fields[vol.Required(area.name, default=default)] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=options, translation_key="area_schedule")
        )
    return vol.Schema(fields)


def _chosen(user_input: dict[str, Any], areas: list[Area], schedules: list[tuple[str, str]]) -> dict[Area, str]:
    """Area -> schedule choice key, for every area picked."""
    if len(schedules) == 1:
        picked = set(user_input.get("areas", []))
        return {area: schedules[0][0] for area in areas if area.area_id in picked}
    keys = {key for key, _ in schedules}
    return {area: user_input[area.name] for area in areas if user_input.get(area.name) in keys}


def _counts(result: SetupResult) -> list[str]:
    counts = []
    for count, noun in ((result.zones, "zone"), (result.automations, "room automation"), (result.flares, "flare")):
        if count:
            counts.append(f"{count} {noun}{'' if count == 1 else 's'}")
    return counts


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


class FlareOptionsFlow(config_entries.OptionsFlow):
    """The Zones entry's options: which bulb models need two-step transitions
    (see two_step.py), the zones' tick timing, and the smallest change worth
    sending. The models field is pre-filled with the shipped defaults and is
    the whole list."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        fields: dict = {
            vol.Optional(CONF_TWO_STEP_MODELS, default=""): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
        suggested: dict = {
            CONF_TWO_STEP_MODELS: options.get(CONF_TWO_STEP_MODELS) or "\n".join(DEFAULT_TWO_STEP_MODEL_PATTERNS),
        }
        for key, default, minimum, maximum, step, unit in (
            (CONF_TICK_INTERVAL, DEFAULT_TICK_INTERVAL, 1, 60, 1, "min"),
            (CONF_TICK_GAP, DEFAULT_TICK_GAP, 0, 10, 0.5, "s"),
            (CONF_MIN_BRIGHTNESS_CHANGE, DEFAULT_MIN_BRIGHTNESS_CHANGE, 0, 25, 0.5, "%"),
            (CONF_MIN_COLOR_TEMP_CHANGE, DEFAULT_MIN_COLOR_TEMP_CHANGE, 0, 50, 0.5, "mired"),
        ):
            fields[vol.Required(key, default=options.get(key, default))] = _number(minimum, maximum, step, unit)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested),
        )


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


class SensorSubentryFlow(ConfigSubentryFlow):
    """Adds one schedule sensor, with its own device and entities prefixed by
    the slugified name. Reconfigure exports and imports the schedule; the
    name can't change, since the entity_ids are derived from it."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            slug = slugify(name)
            # Slugified, to match the entity_id prefix schedule_instances() derives.
            for subentry in self._get_entry().subentries.values():
                if slugify(subentry.title) == slug:
                    errors["name"] = "already_configured"
                    break
            if not errors:
                return self.async_create_entry(title=name, unique_id=slug or None, data={})

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(SUBENTRY_FIELDS), user_input or {}),
            errors=errors,
        )


    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """The schedule as YAML, to copy out or replace. Applying it sets the
        entities, so nothing about the subentry itself changes."""
        instance = schedule_instance_for(self.hass, self._get_reconfigure_subentry().subentry_id)
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                values = parse(user_input["schedule"])
            except ScheduleError as err:
                errors["schedule"] = "invalid_schedule"
                placeholders["error"] = str(err)
            else:
                await async_apply_schedule(self.hass, instance, values)
                return self.async_abort(reason="schedule_imported")

        text = user_input["schedule"] if user_input else dump(read_schedule(self.hass, instance))
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required("schedule"): selector.TextSelector(selector.TextSelectorConfig(multiline=True))}),
                {"schedule": text},
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


class ZoneSubentryFlow(ConfigSubentryFlow):
    """Adds one zone (a "state" subentry). Which lights it tracks is decided
    by callers passing its zone_device_id."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._async_form(user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Lets a zone be renamed without losing it."""
        return await self._async_form(user_input, reconfigure=self._get_reconfigure_subentry())

    async def _async_form(self, user_input, reconfigure=None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            slug = slugify(name)
            for subentry_id, subentry in self._get_entry().subentries.items():
                if reconfigure is not None and subentry_id == reconfigure.subentry_id:
                    continue
                if slugify(subentry.title) == slug:
                    errors["name"] = "already_configured"
                    break
            if not errors:
                if reconfigure is not None:
                    return self.async_update_and_abort(self._get_entry(), reconfigure, title=name)
                return self.async_create_entry(title=name, unique_id=slug or None, data={})

        suggested = user_input or ({"name": reconfigure.title} if reconfigure else {})
        return self.async_show_form(
            step_id="reconfigure" if reconfigure else "user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(SUBENTRY_FIELDS),
                suggested,
            ),
            errors=errors,
        )


class FlareSubentryFlow(ConfigSubentryFlow):
    """Adds one flare: a light over an automation. A room automation from our
    blueprint fills in its lights and zone; any other automation names the
    inputs holding them, or, with no inputs, its lights directly."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._entity_id: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["blueprint", "custom"])

    async def async_step_blueprint(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Every FLARE room automation without a flare, all ticked. Each one
        picked gets a flare named after it, in its area."""
        automations = await automations_using_our_blueprint(self.hass)
        if not automations:
            return self.async_abort(reason="no_room_automations")
        entry = self._get_entry()
        flared = {subentry.data.get(CONF_AUTOMATION) for subentry in entry.subentries.values()}
        candidates = [
            a
            for a in automations
            if automation_ref(self.hass, a) not in flared and (blueprint_inputs(self.hass, a) or {}).get(BLUEPRINT_LIGHTS_INPUT)
        ]
        if not candidates:
            return self.async_abort(reason="every_room_has_a_flare")

        if user_input is not None:
            chosen = [a for a in candidates if a in user_input[CONF_AUTOMATION]]
            for entity_id in chosen:
                self.hass.config_entries.async_add_subentry(entry, room_flare(self.hass, entry, entity_id, self._label(entity_id)))
            return self.async_abort(reason="flares_added", description_placeholders={"count": str(len(chosen))})

        options = [selector.SelectOptionDict(value=a, label=self._label(a)) for a in candidates]
        return self.async_show_form(
            step_id="blueprint",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTOMATION, default=candidates): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, multiple=True, mode=selector.SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    async def async_step_custom(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            self._choose(user_input[CONF_AUTOMATION])
            if await async_automation_blueprint(self.hass, user_input[CONF_AUTOMATION]) is None:
                return await self.async_step_custom_target()
            return await self.async_step_custom_inputs()
        return self.async_show_form(
            step_id="custom",
            data_schema=vol.Schema(
                {vol.Required(CONF_AUTOMATION): selector.EntitySelector(selector.EntitySelectorConfig(domain="automation"))}
            ),
        )

    async def async_step_custom_inputs(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """For an automation from any blueprint: which inputs hold its lights and zone."""
        blueprint = await async_automation_blueprint(self.hass, self._entity_id)
        kinds = lights_input_kinds(blueprint) if blueprint else {}
        errors: dict[str, str] = {}
        if user_input is not None:
            lights_input = user_input[CONF_LIGHTS_INPUT]
            if not (blueprint_inputs(self.hass, self._entity_id) or {}).get(lights_input):
                errors[CONF_LIGHTS_INPUT] = "input_not_set"
            else:
                self._data.update(
                    {
                        CONF_LIGHTS_INPUT: lights_input,
                        CONF_LIGHTS_INPUT_KIND: kinds.get(lights_input, TARGET),
                        CONF_ZONE_INPUT: user_input.get(CONF_ZONE_INPUT) or None,
                    }
                )
                return await self.async_step_details()
        if not kinds:
            return self.async_abort(reason="no_light_inputs")
        return self.async_show_form(
            step_id="custom_inputs",
            data_schema=self.add_suggested_values_to_schema(_inputs_schema(kinds, zone_inputs(blueprint)), user_input or {}),
            errors=errors,
        )

    async def async_step_custom_target(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """For a plain automation: its lights, picked directly."""
        if user_input is not None:
            self._data[CONF_LIGHTS_TARGET] = user_input[CONF_LIGHTS_TARGET]
            return await self.async_step_details()
        return self.async_show_form(step_id="custom_target", data_schema=_TARGET_SCHEMA)

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Name, and the area the flare starts out in."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            if _name_taken(self._get_entry(), name):
                errors["name"] = "already_configured"
            else:
                return self.async_create_entry(
                    title=name,
                    unique_id=slugify(name) or None,
                    data={
                        **self._data,
                        CONF_AREA: user_input.get(CONF_AREA),
                    },
                )
        entry = er.async_get(self.hass).async_get(self._entity_id)
        suggested = {
            "name": self._label(self._entity_id),
            CONF_AREA: entry.area_id if entry else None,
        }
        fields = {
            vol.Required("name"): selector.TextSelector(),
            vol.Optional(CONF_AREA): selector.AreaSelector(),
        }
        return self.async_show_form(
            step_id="details",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(fields), user_input or suggested
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Rename, or pick a different input or lights. The
        area isn't here: once the device exists, its area is the user's."""
        subentry = self._get_reconfigure_subentry()
        data = dict(subentry.data)
        entity_id = automation_entity_id(self.hass, data)
        fields: dict = {vol.Required("name"): selector.TextSelector()}
        # The same fields for every flare, however it was added.
        if data.get(CONF_LIGHTS_TARGET):
            fields.update(_TARGET_SCHEMA.schema)
        else:
            blueprint = await async_automation_blueprint(self.hass, entity_id) if entity_id else None
            if blueprint is not None:
                fields.update(_inputs_schema(lights_input_kinds(blueprint), zone_inputs(blueprint)).schema)

        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            if _name_taken(self._get_entry(), name, skip=subentry.subentry_id):
                errors["name"] = "already_configured"
            else:
                # A setting flares no longer have.
                data.pop("turn_off", None)
                if CONF_LIGHTS_TARGET in user_input:
                    data[CONF_LIGHTS_TARGET] = user_input[CONF_LIGHTS_TARGET]
                if CONF_LIGHTS_INPUT in user_input:
                    blueprint = await async_automation_blueprint(self.hass, entity_id)
                    data[CONF_LIGHTS_INPUT] = user_input[CONF_LIGHTS_INPUT]
                    data[CONF_LIGHTS_INPUT_KIND] = lights_input_kinds(blueprint).get(user_input[CONF_LIGHTS_INPUT], TARGET)
                    data[CONF_ZONE_INPUT] = user_input.get(CONF_ZONE_INPUT) or None
                return self.async_update_and_abort(self._get_entry(), subentry, title=name, data=data)

        suggested = user_input or {"name": subentry.title, **data}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested),
            errors=errors,
            description_placeholders={"automation": self._label(entity_id) if entity_id else data[CONF_AUTOMATION]},
        )

    def _choose(self, entity_id: str) -> None:
        self._entity_id = entity_id
        self._data = {CONF_AUTOMATION: automation_ref(self.hass, entity_id)}

    def _label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id


_TARGET_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LIGHTS_TARGET): selector.TargetSelector(
            selector.TargetSelectorConfig(entity=selector.EntityFilterSelectorConfig(domain="light"))
        )
    }
)


def _inputs_schema(kinds: dict[str, str], zones: list[str]) -> vol.Schema:
    fields: dict = {
        vol.Required(CONF_LIGHTS_INPUT): selector.SelectSelector(selector.SelectSelectorConfig(options=sorted(kinds)))
    }
    if zones:
        fields[vol.Optional(CONF_ZONE_INPUT)] = selector.SelectSelector(selector.SelectSelectorConfig(options=sorted(zones)))
    return vol.Schema(fields)


def _name_taken(entry: ConfigEntry, name: str, skip: str | None = None) -> bool:
    slug = slugify(name)
    return any(
        slugify(subentry.title) == slug for subentry_id, subentry in entry.subentries.items() if subentry_id != skip
    )
