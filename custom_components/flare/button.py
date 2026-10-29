"""A "Clear" button that discards every claim - the escape hatch for
lights stuck "overridden"."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .sensor import settings_device_info
from .tracking.claims import SIGNAL_CLAIMS_UPDATED, ClaimRegistry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    registry: ClaimRegistry = entry.runtime_data
    async_add_entities([_ClearButton(hass, registry, entry)])


class _ClearButton(ButtonEntity):
    """Discards every claim, not just overridden ones, so it's a guaranteed
    reset. Healthy lights are unprotected until their next write."""

    _attr_has_entity_name = False
    _attr_name = "FLARE clear"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:broom"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, entry: ConfigEntry) -> None:
        self.hass = hass
        self._registry = registry
        self._attr_unique_id = f"{entry.entry_id}_clear"
        self._attr_translation_key = "clear"
        self.entity_id = "button.flare_clear"
        self._attr_device_info = settings_device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CLAIMS_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_press(self) -> None:
        await self._registry.async_clear(sorted(self._registry.all_records()), announce=True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"tracked": len(self._registry.all_records())}
