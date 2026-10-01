"""Config flow for FLARE.

Adding the integration creates both the Schedules and Tracking entries.
Schedule sensors are "sensor" subentries, added and named by the user;
their times and curve values are entities on the sensor's device."""

from __future__ import annotations

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
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_ENTRY_TYPE,
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
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_TRACKING,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_STATE,
    ZONES_ENTRY_TITLE,
)
from .services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS

SUBENTRY_FIELDS = {vol.Required("name"): selector.TextSelector()}


class AdaptiveLightingHelpersConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """One "Add FLARE" creates both entries, asking only which rooms to track.

        The flow visibly completes on Schedules because it creates no devices:
        HA's "integration added" dialog prompts to rename every device the
        completing entry has, with no way to suppress it. Tracking, which seeds
        a device per room, is created through SOURCE_IMPORT instead."""
        configured = {entry.data.get(CONF_ENTRY_TYPE) for entry in self._async_current_entries()}
        needs_schedules = ENTRY_TYPE_SCHEDULES not in configured
        needs_tracking = ENTRY_TYPE_TRACKING not in configured

        # Pre-selects every area with a light. Areas with none are left out.
        areas = _areas_with_lights(self.hass) if needs_tracking else []
        if areas and user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Optional("areas", default=[area_id for area_id, _ in areas]): selector.AreaSelector(
                            selector.AreaSelectorConfig(multiple=True)
                        )
                    }
                ),
            )

        # With nothing left to create, _create_schedules_entry's unique_id guard
        # aborts with already_configured.
        chosen = [(a, n) for a, n in areas if a in (user_input or {}).get("areas", [])]
        if needs_tracking and not needs_schedules:
            return await self._create_tracking_entry(chosen)
        if needs_tracking:
            await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={"areas": [area_id for area_id, _ in chosen]},
            )
        return await self._create_schedules_entry()

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Creates the tracking entry without a visible flow (see async_step_user)."""
        chosen = import_data["areas"]
        areas = [(a, n) for a, n in _areas_with_lights(self.hass) if a in chosen]
        return await self._create_tracking_entry(areas)

    async def _create_schedules_entry(self) -> FlowResult:
        """Nothing to ask; schedule sensors are added afterwards as subentries."""
        await self.async_set_unique_id(f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="FLARE Schedules", data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES}
        )

    async def _create_tracking_entry(self, areas: list[tuple[str, str]]) -> FlowResult:
        await self.async_set_unique_id(f"{DOMAIN}_{ENTRY_TYPE_TRACKING}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=ZONES_ENTRY_TITLE,
            data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING},
            subentries=[
                {
                    "subentry_type": SUBENTRY_TYPE_STATE,
                    "title": name,
                    "unique_id": slugify(name),
                    "data": {},
                }
                for area_id, name in areas
            ],
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TRACKING:
            return {SUBENTRY_TYPE_STATE: StateSubentryFlow}
        return {SUBENTRY_TYPE_SENSOR: SensorSubentryFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        return AdaptiveLightingHelpersOptionsFlow()


class AdaptiveLightingHelpersOptionsFlow(config_entries.OptionsFlow):
    """Which bulb models need two-step transitions (see two_step.py), and on
    the Zones entry, the zones' tick timing and the smallest change worth
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
        if self.config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TRACKING:
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
    the slugified name. No reconfigure flow: everything but the name is an
    entity."""

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


def _areas_with_lights(hass) -> list[tuple[str, str]]:
    """(area_id, name) for every area holding a light, by the entity's own
    area or its device's."""
    from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    area_ids = set()
    for entry in entity_registry.entities.values():
        if entry.domain != "light":
            continue
        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = device_registry.async_get(entry.device_id)
            area_id = device.area_id if device else None
        if area_id:
            area_ids.add(area_id)
    area_registry = ar.async_get(hass)
    named = []
    for area_id in area_ids:
        area = area_registry.async_get_area(area_id)
        if area is not None:
            named.append((area_id, area.name))
    return sorted(named, key=lambda pair: pair[1])


class StateSubentryFlow(ConfigSubentryFlow):
    """Adds one zone (a "state" subentry). Which lights it tracks is decided
    by callers passing its tracking_device_id."""

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
