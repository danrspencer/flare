"""Bulbs: colour temperature and brightness, kept across restarts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import DOMAIN, Room


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        Bulb(room, n) for room in hass.data[DOMAIN] for n in range(1, room.bulbs + 1)
    )


class Bulb(LightEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_min_color_temp_kelvin = 2200
    _attr_max_color_temp_kelvin = 6500

    def __init__(self, room: Room, number: int) -> None:
        self._attr_unique_id = f"{room.slug}_{number}"
        self._attr_device_info = room.bulb_device(number)
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_color_temp_kelvin = 2700

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) is None:
            return
        self._attr_is_on = last.state == STATE_ON
        self._attr_brightness = last.attributes.get(ATTR_BRIGHTNESS) or self._attr_brightness
        self._attr_color_temp_kelvin = (
            last.attributes.get(ATTR_COLOR_TEMP_KELVIN) or self._attr_color_temp_kelvin
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._attr_brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
        if (kelvin := kwargs.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
            self._attr_color_temp_kelvin = max(
                self._attr_min_color_temp_kelvin, min(self._attr_max_color_temp_kelvin, kelvin)
            )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
