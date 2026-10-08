"""Describes FLARE's zone events in the logbook. Each is filed under one of
the zone's count sensors and its device, so it shows in the zone's
Activity and in a logbook card targeting the zone. Worded as hand-overs,
not failures."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_ENTITY_ID, LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_LIGHT_OVERRIDDEN, EVENT_LIGHTS_CONTROLLED, EVENT_LIGHTS_RELEASED


def _plural(count: int) -> str:
    return f"{count} light{'' if count == 1 else 's'}"


def _light_name(hass: HomeAssistant, entity_id: str | None) -> str:
    state = hass.states.get(entity_id) if entity_id else None
    return state.name if state else (entity_id or "a light")


def _entry(data, message: str) -> dict[str, str]:
    """Filed under the count sensor the event names. Read with .get: one
    describer raising breaks the whole logbook."""
    entry = {LOGBOOK_ENTRY_NAME: data.get("zone") or "FLARE", LOGBOOK_ENTRY_MESSAGE: message}
    if data.get("entity_id"):
        entry[LOGBOOK_ENTRY_ENTITY_ID] = data["entity_id"]
    return entry


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe FLARE's logbook events."""

    @callback
    def async_describe_override(event: Event) -> dict[str, str]:
        data = event.data
        live = data.get("live") or {}
        target = (data.get("latest") or {}).get("target") or {}
        # What was asked for against what is actually there, in the same
        # terms: RGB against RGB, colour temperature against colour temperature.
        detail = ""
        if target.get("brightness") is not None:
            colour = "rgb_color" if target.get("rgb_color") is not None else "color_temp_kelvin"
            asked = f"{target.get('brightness')}/{target.get(colour)}"
            found = f"{live.get('brightness')}/{live.get(colour)}"
            detail = f" (last asked for {asked}, found {found})"
        light = _light_name(hass, data.get("light"))
        return _entry(data, f"released {light} to something else{detail}")

    @callback
    def async_describe_controlled(event: Event) -> dict[str, str]:
        return _entry(event.data, f"now controlling {_plural(event.data.get('controlled', 0))}")

    @callback
    def async_describe_released(event: Event) -> dict[str, str]:
        return _entry(event.data, f"cleared {_plural(len(event.data.get('lights') or []))}")

    async_describe_event(DOMAIN, EVENT_LIGHT_OVERRIDDEN, async_describe_override)
    async_describe_event(DOMAIN, EVENT_LIGHTS_CONTROLLED, async_describe_controlled)
    async_describe_event(DOMAIN, EVENT_LIGHTS_RELEASED, async_describe_released)
