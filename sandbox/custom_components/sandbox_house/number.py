"""Each room's Daylight: how bright it is without its lights, in lux."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DOMAIN, Room


def daylight_signal(room: Room) -> str:
    return f"{DOMAIN}_daylight_{room.slug}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(Daylight(room) for room in hass.data[DOMAIN])


class Daylight(NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Daylight"
    _attr_icon = "mdi:white-balance-sunny"
    _attr_native_min_value = 0
    _attr_native_max_value = 2000
    _attr_native_step = 10
    _attr_native_unit_of_measurement = LIGHT_LUX
    _attr_mode = NumberMode.SLIDER

    def __init__(self, room: Room) -> None:
        self._room = room
        self._attr_unique_id = f"{room.slug}_daylight"
        self._attr_device_info = room.sensor_device()
        self._attr_native_value = 0

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, daylight_signal(self._room), value)
