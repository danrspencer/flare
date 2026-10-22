"""A room's TV, which only turns on and off: enough for a template to
ask whether it's on."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import DOMAIN, Room


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(TV(room) for room in hass.data[DOMAIN] if room.tv)


class TV(MediaPlayerEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF

    def __init__(self, room: Room) -> None:
        self._attr_unique_id = f"{room.slug}_tv"
        self._attr_device_info = room.tv_device()
        self._attr_state = MediaPlayerState.OFF

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) is not None and last.state == MediaPlayerState.ON:
            self._attr_state = MediaPlayerState.ON

    async def async_turn_on(self) -> None:
        self._attr_state = MediaPlayerState.ON
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        self._attr_state = MediaPlayerState.OFF
        self.async_write_ha_state()
