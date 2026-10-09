"""Which lights are flares. A flare must never be one of a room's lights:
the room's tick would send it the curve, and it would pass that on to every
light as an override."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN


def is_flare_entry(entry: er.RegistryEntry | None) -> bool:
    """True for a flare's own light's registry entry."""
    return entry is not None and entry.platform == DOMAIN and entry.domain == "light"


def is_flare_light(hass: HomeAssistant, entity_id: str) -> bool:
    return is_flare_entry(er.async_get(hass).async_get(entity_id))


def without_flares(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """`entity_ids` less any flare lights, in order."""
    return [e for e in entity_ids if not is_flare_light(hass, e)]
