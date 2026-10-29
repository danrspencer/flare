"""Each room's illuminance sensor, following its Daylight."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DOMAIN, Room
from .number import daylight_signal


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(Illuminance(room) for room in hass.data[DOMAIN])


class Illuminance(SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = LIGHT_LUX

    def __init__(self, room: Room) -> None:
        self._room = room
        self._attr_unique_id = f"{room.slug}_illuminance"
        self._attr_device_info = room.sensor_device()
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, daylight_signal(self._room), self._daylight)
        )

    @callback
    def _daylight(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
