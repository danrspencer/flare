"""Bulbs: colour temperature and brightness, kept across restarts.

Without power (its own Power switch or the room's Wall switch off) a bulb is
unavailable. When power comes back it boots as a real bulb does: on, at its
default, ignoring commands for BOOT seconds."""

from __future__ import annotations

from datetime import timedelta
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import DOMAIN, Room, power_signal

# How long a bulb ignores commands after power comes back.
BOOT = timedelta(seconds=1)
DEFAULT_BRIGHTNESS = 255
DEFAULT_KELVIN = 2700


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
        self._room = room
        self._number = number
        self._attr_unique_id = f"{room.slug}_{number}"
        self._attr_device_info = room.bulb_device(number)
        self._attr_is_on = False
        self._attr_brightness = DEFAULT_BRIGHTNESS
        self._attr_color_temp_kelvin = DEFAULT_KELVIN
        # Which of the bulb's own Power and the room's Wall switch are on.
        self._power = {"bulb": True, "wall": True}
        self._booted_at = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, power_signal(self._room, self._number), self._set_power)
        )
        if (last := await self.async_get_last_state()) is None:
            return
        self._attr_is_on = last.state == STATE_ON
        self._attr_brightness = last.attributes.get(ATTR_BRIGHTNESS) or self._attr_brightness
        self._attr_color_temp_kelvin = (
            last.attributes.get(ATTR_COLOR_TEMP_KELVIN) or self._attr_color_temp_kelvin
        )

    @callback
    def _set_power(self, source: str, on: bool) -> None:
        was_powered = all(self._power.values())
        self._power[source] = on
        powered = all(self._power.values())
        if powered == was_powered:
            return
        self._attr_available = powered
        if powered:
            self._attr_is_on = True
            self._attr_brightness = DEFAULT_BRIGHTNESS
            self._attr_color_temp_kelvin = DEFAULT_KELVIN
            self._booted_at = dt_util.utcnow()
        self.async_write_ha_state()

    def _booting(self) -> bool:
        return self._booted_at is not None and dt_util.utcnow() < self._booted_at + BOOT

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._booting():
            return
        self._attr_is_on = True
        self._attr_brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
        if (kelvin := kwargs.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
            self._attr_color_temp_kelvin = max(
                self._attr_min_color_temp_kelvin, min(self._attr_max_color_temp_kelvin, kelvin)
            )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._booting():
            return
        self._attr_is_on = False
        self.async_write_ha_state()
