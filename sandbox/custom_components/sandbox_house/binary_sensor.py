"""Each room's occupancy sensor, following its Presence switch."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DOMAIN, Room
from .switch import presence_signal


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(Occupancy(room) for room in hass.data[DOMAIN])


class Occupancy(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, room: Room) -> None:
        self._room = room
        self._attr_unique_id = f"{room.slug}_occupancy"
        self._attr_device_info = room.sensor_device()
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, presence_signal(self._room), self._presence)
        )

    @callback
    def _presence(self, on: bool) -> None:
        self._attr_is_on = on
        self.async_write_ha_state()
