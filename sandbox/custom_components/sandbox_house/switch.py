"""Each room's Presence switch: someone is in the room while it's on."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DOMAIN, Room


def presence_signal(room: Room) -> str:
    return f"{DOMAIN}_presence_{room.slug}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(Presence(room) for room in hass.data[DOMAIN])


class Presence(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Presence"
    _attr_icon = "mdi:walk"

    def __init__(self, room: Room) -> None:
        self._room = room
        self._attr_unique_id = f"{room.slug}_presence"
        self._attr_device_info = room.sensor_device()
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set(False)

    def _set(self, on: bool) -> None:
        self._attr_is_on = on
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, presence_signal(self._room), on)
