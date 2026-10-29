"""The Settings entry's diagnostics download: every claim and room as FLARE
holds them, for bug reports."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ENTRY_TYPE, ENTRY_TYPE_SETTINGS


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_SETTINGS:
        return {"options": dict(entry.options)}
    registry = entry.runtime_data
    return {"options": dict(entry.options), "claims": registry.all_records(), "rooms": dict(registry.rooms)}
