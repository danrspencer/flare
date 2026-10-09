"""flare.export_schedule and flare.import_schedule: a schedule's times and
curve values as one YAML document (see schedule/transfer.py).

Registered once for the domain, not by either entry, since they need only
the schedule's own entities. Importing sets those entities through their
own services, exactly as moving their sliders does."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import Context, HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from ..const import DOMAIN, SUBENTRY_TYPE_SENSOR, is_reachable
from ..schedule.coordinator import CURVE_KEYS, TIME_KEYS, ScheduleInstance, schedule_instances
from ..schedule.transfer import ScheduleError, dump, parse

ATTR_SCHEDULE_DEVICE_ID = "schedule_device_id"
ATTR_SCHEDULE = "schedule"


def resolve_schedule(hass: HomeAssistant, device_id: str) -> ScheduleInstance:
    """The schedule behind a FLARE Schedule device, or a validation error."""
    device = dr.async_get(hass).async_get(device_id)
    subentry_ids = {ident for domain, ident in device.identifiers if domain == DOMAIN} if device else set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        for instance in schedule_instances(entry):
            if instance.subentry_id in subentry_ids:
                return instance
    raise ServiceValidationError(f"{device_id} is not a FLARE schedule")


def schedule_instance_for(hass: HomeAssistant, subentry_id: str) -> ScheduleInstance:
    """The schedule for one of the Schedules entry's own subentries."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        subentry = entry.subentries.get(subentry_id)
        if subentry is not None and subentry.subentry_type == SUBENTRY_TYPE_SENSOR:
            return next(i for i in schedule_instances(entry) if i.subentry_id == subentry_id)
    raise ValueError(f"No schedule with subentry {subentry_id}")


def read_schedule(hass: HomeAssistant, instance: ScheduleInstance) -> dict[str, str | int]:
    """The schedule's current values, skipping any entity not yet available."""
    values: dict[str, str | int] = {}
    for key in TIME_KEYS:
        state = hass.states.get(instance.time_entity(hass, key))
        if is_reachable(state):
            values[key] = state.state
    for key in CURVE_KEYS:
        state = hass.states.get(instance.number_entity(hass, key))
        if is_reachable(state):
            values[key] = round(float(state.state))
    return values


async def async_apply_schedule(
    hass: HomeAssistant, instance: ScheduleInstance, values: dict[str, str | int], context: Context | None = None
) -> None:
    """Sets each value through its entity's own service. `values` is already
    validated, so nothing is set unless all of it can be."""
    for key, value in values.items():
        if key in TIME_KEYS:
            domain, entity_id, data = "time", instance.time_entity(hass, key), {"time": value}
        else:
            domain, entity_id, data = "number", instance.number_entity(hass, key), {"value": value}
        await hass.services.async_call(
            domain, "set_value", {"entity_id": entity_id, **data}, blocking=True, context=context
        )


def parse_schedule(document: Any) -> dict[str, str | int]:
    """Text, or a mapping from YAML service data, into validated values."""
    text = document if isinstance(document, str) else _mapping_to_text(document)
    try:
        return parse(text)
    except ScheduleError as err:
        raise ServiceValidationError(str(err)) from err


def _mapping_to_text(document: Any) -> str:
    """A mapping passed straight in YAML service data already has typed
    values, so it goes back through the same text parser as a pasted one."""
    import yaml

    return yaml.safe_dump(document)


def async_setup_schedule_services(hass: HomeAssistant) -> None:
    async def export_schedule(call: ServiceCall) -> ServiceResponse:
        """flare.export_schedule - see services.yaml."""
        instance = resolve_schedule(hass, call.data[ATTR_SCHEDULE_DEVICE_ID])
        return {"schedule": dump(read_schedule(hass, instance))}

    async def import_schedule(call: ServiceCall) -> None:
        """flare.import_schedule - see services.yaml."""
        instance = resolve_schedule(hass, call.data[ATTR_SCHEDULE_DEVICE_ID])
        values = parse_schedule(call.data[ATTR_SCHEDULE])
        await async_apply_schedule(hass, instance, values, call.context)

    hass.services.async_register(
        DOMAIN,
        "export_schedule",
        export_schedule,
        schema=vol.Schema({vol.Required(ATTR_SCHEDULE_DEVICE_ID): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "import_schedule",
        import_schedule,
        schema=vol.Schema(
            {vol.Required(ATTR_SCHEDULE_DEVICE_ID): cv.string, vol.Required(ATTR_SCHEDULE): vol.Any(str, dict)}
        ),
    )
