"""A per-zone "Clear" button that discards the zone's claims - the
escape hatch for a light stuck "overridden"."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .zone.instance import ZoneInstance, zone_instances
from .zone.claims import SIGNAL_CLAIMS_UPDATED, ClaimRegistry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    registry: ClaimRegistry = hass.data[DOMAIN][entry.entry_id]
    for instance in zone_instances(entry):
        async_add_entities(
            [_ZoneClearButton(hass, registry, instance)], config_subentry_id=instance.subentry_id
        )


class _ZoneClearButton(ButtonEntity):
    """Discards every claim in the zone, not just overridden ones, so
    it's a guaranteed reset. Healthy lights are unprotected until their
    next write."""

    _attr_has_entity_name = True
    _attr_name = "Clear"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:broom"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, instance: ZoneInstance) -> None:
        self.hass = hass
        self._registry = registry
        self._instance = instance
        self._attr_unique_id = f"{instance.subentry_id}_clear"
        self.entity_id = f"button.{instance.prefix}flare_clear"
        self._attr_device_info = instance.device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CLAIMS_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _tracked(self) -> list[str]:
        return sorted(self._registry.records_for_zone(self._instance.subentry_id))

    async def async_press(self) -> None:
        await self._registry.async_clear(self._instance.subentry_id, self._tracked(), announce=True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"tracked": len(self._tracked())}
