"""Describes EVENT_LIGHT_OVERRIDDEN in the logbook, so it shows on the
light's timeline and the state device's Activity. Worded as a hand-over,
not a failure."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_ENTITY_ID, LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_LIGHT_OVERRIDDEN


def _describe_scope(scope: str | None) -> str:
    return scope or "adaptive lighting"


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe adaptive lighting logbook events."""

    @callback
    def async_describe_override(event: Event) -> dict[str, str]:
        data = event.data
        live = data.get("live") or {}
        latest = data.get("latest") or {}
        target = latest.get("target") or {}
        # What was asked for against what is actually there.
        if target:
            asked = f"{target.get('brightness')}/{target.get('color_temp_kelvin') or target.get('rgb_color')}"
            found = f"{live.get('brightness')}/{live.get('color_temp_kelvin') or live.get('rgb_color')}"
            detail = f" (last asked for {asked}, found {found})"
        else:
            detail = ""
        return {
            LOGBOOK_ENTRY_NAME: _describe_scope(data.get("scope")),
            LOGBOOK_ENTRY_MESSAGE: f"released this light to something else{detail}",
            LOGBOOK_ENTRY_ENTITY_ID: data["entity_id"],
        }

    async_describe_event(DOMAIN, EVENT_LIGHT_OVERRIDDEN, async_describe_override)
