"""Adding and reconfiguring schedules, zones and flares: one subentry flow
each, on the entry that holds them."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigSubentryFlow, SubentryFlowResult
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.util import slugify

from .area_setup import room_flare
from .blueprint_check import automations_using_our_blueprint
from .const import (
    BLUEPRINT_LIGHTS_INPUT,
    CONF_AREA,
    CONF_AUTOMATION,
    CONF_LIGHTS_INPUT,
    CONF_LIGHTS_INPUT_KIND,
    CONF_LIGHTS_TARGET,
    CONF_ZONE_INPUT,
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
from .schedule.transfer import ScheduleError, dump, parse
from .services.schedules import async_apply_schedule, read_schedule, schedule_instance_for

SUBENTRY_FIELDS = {vol.Required("name"): selector.TextSelector()}


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
