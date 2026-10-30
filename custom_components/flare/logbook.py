"""Describes FLARE's claim events in the logbook. Each is filed under one
of the count sensors, or Clear for a release, which the logbook shows as
the entry's name, so the message names the room (the automation) it's
about. Worded as hand-overs, not failures."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_ENTITY_ID, LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_LIGHT_OVERRIDDEN, EVENT_LIGHTS_CONTROLLED, EVENT_LIGHTS_RELEASED


def _plural(count: int) -> str:
    return f"{count} light{'' if count == 1 else 's'}"


def _light_name(hass: HomeAssistant, entity_id: str | None) -> str:
    state = hass.states.get(entity_id) if entity_id else None
    return state.name if state else (entity_id or "a light")


def _room_name(hass: HomeAssistant, data) -> str:
    """The room the event is about, by its entity's name, else "FLARE". An
    override names every room the light is in."""
    rooms = data.get("rooms") or ([data["room"]] if data.get("room") else [])
    names = []
    for room in rooms:
        state = hass.states.get(room) if isinstance(room, str) else None
        names.append(state.name if state else str(room))
    return ", ".join(names) or "FLARE"


def _entry(hass: HomeAssistant, data, message: str) -> dict[str, str]:
    """Filed under the entity the event names. Read with .get: one
    describer raising breaks the whole logbook."""
    entry = {LOGBOOK_ENTRY_NAME: _room_name(hass, data), LOGBOOK_ENTRY_MESSAGE: message}
    if data.get(ATTR_ENTITY_ID):
        entry[LOGBOOK_ENTRY_ENTITY_ID] = data[ATTR_ENTITY_ID]
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
        return _entry(hass, data, f"{_room_name(hass, data)} released {light} to something else{detail}")

    @callback
    def async_describe_controlled(event: Event) -> dict[str, str]:
        controlled = _plural(event.data.get("controlled", 0))
        return _entry(hass, event.data, f"{_room_name(hass, event.data)} is now controlling {controlled}")

    @callback
    def async_describe_released(event: Event) -> dict[str, str]:
        cleared = _plural(len(event.data.get("lights") or []))
        return _entry(hass, event.data, f"{_room_name(hass, event.data)} cleared {cleared}")

    async_describe_event(DOMAIN, EVENT_LIGHT_OVERRIDDEN, async_describe_override)
    async_describe_event(DOMAIN, EVENT_LIGHTS_CONTROLLED, async_describe_controlled)
    async_describe_event(DOMAIN, EVENT_LIGHTS_RELEASED, async_describe_released)
