"""Describes FLARE's zone events in the logbook. Each is filed under one of
the zone's count sensors and its device, so it shows in the zone's
Activity and in a logbook card targeting the zone. Worded as hand-overs,
not failures."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_ENTITY_ID, LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_LIGHT_OVERRIDDEN, EVENT_LIGHTS_CONTROLLED, EVENT_LIGHTS_RELEASED


def _describe_zone(zone: str | None) -> str:
    return zone or "FLARE"


def _filed_under(data) -> dict[str, str]:
    """The entity the entry links to. Events recorded before 1.0.0 have none,
    or the light itself."""
    return {LOGBOOK_ENTRY_ENTITY_ID: data["entity_id"]} if data.get("entity_id") else {}


def _light_of(data) -> str | None:
    """The light an override names: `light`, or before 1.0.0 `entity_id`."""
    return data.get("light") or data.get("entity_id")


def _light_name(hass: HomeAssistant, entity_id: str | None) -> str:
    state = hass.states.get(entity_id) if entity_id else None
    return state.name if state else (entity_id or "a light")


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
        latest = data.get("latest") or {}
        target = latest.get("target") or {}
        # What was asked for against what is actually there, in the same
        # terms: RGB against RGB, colour temperature against colour temperature.
        if target.get("brightness") is not None:
            colour = "rgb_color" if target.get("rgb_color") is not None else "color_temp_kelvin"
            asked = f"{target.get('brightness')}/{target.get(colour)}"
            found = f"{live.get('brightness')}/{live.get(colour)}"
            detail = f" (last asked for {asked}, found {found})"
        else:
            detail = ""
        return {
            LOGBOOK_ENTRY_NAME: _describe_zone(data.get("zone")),
            LOGBOOK_ENTRY_MESSAGE: f"released {_light_name(hass, _light_of(data))} to something else{detail}",
            **_filed_under(data),
        }

    @callback
    def async_describe_controlled(event: Event) -> dict[str, str]:
        count = event.data.get("controlled", 0)
        return {
            LOGBOOK_ENTRY_NAME: _describe_zone(event.data.get("zone")),
            LOGBOOK_ENTRY_MESSAGE: f"now controlling {count} light{'' if count == 1 else 's'}",
            **_filed_under(event.data),
        }

    async_describe_event(DOMAIN, EVENT_LIGHT_OVERRIDDEN, async_describe_override)
    async_describe_event(DOMAIN, EVENT_LIGHTS_CONTROLLED, async_describe_controlled)
    @callback
    def async_describe_released(event: Event) -> dict[str, str]:
        count = len(event.data.get("lights") or [])
        return {
            LOGBOOK_ENTRY_NAME: _describe_zone(event.data.get("zone")),
            LOGBOOK_ENTRY_MESSAGE: f"cleared {count} light{'' if count == 1 else 's'}",
            **_filed_under(event.data),
        }

    async_describe_event(DOMAIN, EVENT_LIGHTS_RELEASED, async_describe_released)
