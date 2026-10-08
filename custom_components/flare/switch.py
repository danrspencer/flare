"""Sticky phase override switch, one per schedule. When off (the
default), a phase override clears itself at the next phase boundary
(see select.py)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .schedule.coordinator import ScheduleInstance, schedule_instances


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    for instance in schedule_instances(entry):
        async_add_entities([_StickyOverrideSwitch(instance)], config_subentry_id=instance.subentry_id)


class _StickyOverrideSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:pin"
    _attr_name = "Sticky Phase Override"

    def __init__(self, instance: ScheduleInstance) -> None:
        self._attr_unique_id = f"{instance.subentry_id}_sticky_phase_override"
        self._attr_translation_key = "sticky_phase_override"
        self.entity_id = instance.sticky_entity_id
        self._attr_device_info = instance.device_info
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
