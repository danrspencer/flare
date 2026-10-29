"""Each room's Presence switch, someone being in the room while it's on;
its Wall switch, cutting every bulb's power; and each bulb's own Power."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DOMAIN, Room, power_signal


def presence_signal(room: Room) -> str:
    return f"{DOMAIN}_presence_{room.slug}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    rooms = hass.data[DOMAIN]
    async_add_entities(Presence(room) for room in rooms)
    async_add_entities(WallSwitch(room) for room in rooms)
    async_add_entities(BulbPower(room, n) for room in rooms for n in range(1, room.bulbs + 1))


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


class _Power(SwitchEntity):
    """On until switched off. Not restored: a restart powers everything."""

    _attr_has_entity_name = True
    _source = ""

    def __init__(self, room: Room, numbers: list[int]) -> None:
        self._room = room
        self._numbers = numbers
        self._attr_is_on = True

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set(False)

    def _set(self, on: bool) -> None:
        self._attr_is_on = on
        self.async_write_ha_state()
        for number in self._numbers:
            async_dispatcher_send(self.hass, power_signal(self._room, number), self._source, on)


class WallSwitch(_Power):
    """Every bulb in the room, as a light switch on the wall."""

    _attr_name = None
    _attr_icon = "mdi:light-switch"
    _source = "wall"

    def __init__(self, room: Room) -> None:
        super().__init__(room, list(range(1, room.bulbs + 1)))
        self._attr_unique_id = f"{room.slug}_wall_switch"
        self._attr_device_info = room.wall_switch_device()


class BulbPower(_Power):
    """One bulb, as if unscrewed or out of range."""

    _attr_name = "Power"
    _attr_icon = "mdi:power-plug"
    _source = "bulb"

    def __init__(self, room: Room, number: int) -> None:
        super().__init__(room, [number])
        self._attr_unique_id = f"{room.slug}_{number}_power"
        self._attr_device_info = room.bulb_device(number)
