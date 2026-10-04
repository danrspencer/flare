"""Describes FLARE's hand-over events in the logbook, so they show on the
light's timeline and the zone's Activity. Worded as hand-overs, not
failures."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_ENTITY_ID, LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_LIGHT_OVERRIDDEN, EVENT_LIGHT_RECLAIMED, EVENT_LIGHTS_CONTROLLED


def _describe_zone(zone: str | None) -> str:
    return zone or "FLARE"


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
        # What was asked for against what is actually there.
        if target.get("brightness") is not None:
            asked = f"{target.get('brightness')}/{target.get('color_temp_kelvin') or target.get('rgb_color')}"
            found = f"{live.get('brightness')}/{live.get('color_temp_kelvin') or live.get('rgb_color')}"
            detail = f" (last asked for {asked}, found {found})"
        else:
            detail = ""
        return {
            LOGBOOK_ENTRY_NAME: _describe_zone(data.get("zone")),
            LOGBOOK_ENTRY_MESSAGE: f"released this light to something else{detail}",
            LOGBOOK_ENTRY_ENTITY_ID: data["entity_id"],
        }

    @callback
    def async_describe_reclaim(event: Event) -> dict[str, str]:
        return {
            LOGBOOK_ENTRY_NAME: _describe_zone(event.data.get("zone")),
            LOGBOOK_ENTRY_MESSAGE: "is setting this light again",
            LOGBOOK_ENTRY_ENTITY_ID: event.data["entity_id"],
        }

    @callback
    def async_describe_controlled(event: Event) -> dict[str, str]:
        count = event.data.get("controlled", 0)
        return {
            LOGBOOK_ENTRY_NAME: _describe_zone(event.data.get("zone")),
            LOGBOOK_ENTRY_MESSAGE: f"is now setting {count} light{'' if count == 1 else 's'}",
        }

    async_describe_event(DOMAIN, EVENT_LIGHT_OVERRIDDEN, async_describe_override)
    async_describe_event(DOMAIN, EVENT_LIGHTS_CONTROLLED, async_describe_controlled)
    async_describe_event(DOMAIN, EVENT_LIGHT_RECLAIMED, async_describe_reclaim)
