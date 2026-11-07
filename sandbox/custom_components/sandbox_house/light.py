"""Bulbs: brightness and colour, kept across restarts.

A plain bulb has colour temperature only. A room's `odd_bulbs` add bulbs that
behave like awkward real ones (KINDS): colour-only strips HA sends Kelvin to
as a colour, bulbs reporting in xy, a dishonest advertised range, coarse
steps, dimmers and on/off switches.

Without power (its own Power switch or the room's Wall switch off) a bulb is
unavailable. When power comes back it boots as a real bulb does: on, at its
default, ignoring commands for BOOT seconds."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_XY_COLOR,
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
from homeassistant.util import color as color_util
from homeassistant.util import dt as dt_util

from . import DOMAIN, Room, power_signal
from .bulbs import KINDS, Kind

# How long a bulb ignores commands after power comes back.
BOOT = timedelta(seconds=1)
DEFAULT_BRIGHTNESS = 255
DEFAULT_KELVIN = 2700

# Each colour mode's attribute, for the modes a bulb keeps a value in.
MODE_ATTRIBUTES = {
    ColorMode.COLOR_TEMP: ATTR_COLOR_TEMP_KELVIN,
    ColorMode.HS: ATTR_HS_COLOR,
    ColorMode.RGB: ATTR_RGB_COLOR,
    ColorMode.RGBW: ATTR_RGBW_COLOR,
    ColorMode.RGBWW: ATTR_RGBWW_COLOR,
    ColorMode.XY: ATTR_XY_COLOR,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        Bulb(room, n, KINDS[room.kind(n)]) for room in hass.data[DOMAIN] for n in range(1, room.bulbs + 1)
    )


class Bulb(LightEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, room: Room, number: int, kind: Kind) -> None:
        self._room = room
        self._number = number
        self._kind = kind
        self._attr_unique_id = f"{room.slug}_{number}"
        self._attr_device_info = room.bulb_device(number)
        self._attr_supported_color_modes = set(kind.modes)
        self._attr_min_color_temp_kelvin = kind.advertised_min_kelvin or kind.min_kelvin
        self._attr_max_color_temp_kelvin = kind.advertised_max_kelvin or kind.max_kelvin
        self._attr_is_on = False
        self._boot_defaults()
        # Which of the bulb's own Power and the room's Wall switch are on.
        self._power = {"bulb": True, "wall": True}
        self._booted_at = None

    def _boot_defaults(self) -> None:
        """Brightness and colour at power-up: full, at DEFAULT_KELVIN in the
        bulb's own terms."""
        modes = self._kind.modes
        self._attr_brightness = None if modes == {ColorMode.ONOFF} else DEFAULT_BRIGHTNESS
        if ColorMode.COLOR_TEMP in modes:
            self._set_kelvin(DEFAULT_KELVIN)
        elif ColorMode.RGBWW in modes:
            self._set(
                ColorMode.RGBWW,
                color_util.color_temperature_to_rgbww(
                    DEFAULT_KELVIN, DEFAULT_BRIGHTNESS, self._kind.min_kelvin, self._kind.max_kelvin
                ),
            )
        elif modes & {ColorMode.HS, ColorMode.RGB, ColorMode.RGBW, ColorMode.XY}:
            hs = color_util.color_temperature_to_hs(DEFAULT_KELVIN)
            rgb = color_util.color_hs_to_RGB(*hs)
            if ColorMode.HS in modes:
                self._set(ColorMode.HS, hs)
            elif ColorMode.RGB in modes:
                self._set(ColorMode.RGB, rgb)
            elif ColorMode.RGBW in modes:
                self._set(ColorMode.RGBW, color_util.color_rgb_to_rgbw(*rgb))
            else:
                self._set(ColorMode.XY, color_util.color_hs_to_xy(*hs))
        else:
            self._attr_color_mode = next(iter(modes))

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, power_signal(self._room, self._number), self._set_power)
        )
        if (last := await self.async_get_last_state()) is None:
            return
        self._attr_is_on = last.state == STATE_ON
        if self._attr_brightness is not None:
            self._attr_brightness = last.attributes.get(ATTR_BRIGHTNESS) or self._attr_brightness
        mode = last.attributes.get(ATTR_COLOR_MODE)
        if mode in self._kind.modes and mode in MODE_ATTRIBUTES:
            value = last.attributes.get(MODE_ATTRIBUTES[mode])
            if value is not None:
                self._set(ColorMode(mode), value)

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
            self._boot_defaults()
            self._booted_at = dt_util.utcnow()
        self.async_write_ha_state()

    def _booting(self) -> bool:
        return self._booted_at is not None and dt_util.utcnow() < self._booted_at + BOOT

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._booting():
            return
        self._attr_is_on = True
        if self._attr_brightness is not None and (brightness := kwargs.get(ATTR_BRIGHTNESS)) is not None:
            self._attr_brightness = (
                max(1, round(round(brightness / 2.55) * 2.55)) if self._kind.coarse else brightness
            )
        if (kelvin := kwargs.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
            self._set_kelvin(kelvin)
        for mode, attribute in MODE_ATTRIBUTES.items():
            if mode != ColorMode.COLOR_TEMP and (value := kwargs.get(attribute)) is not None:
                self._set(mode, value)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._booting():
            return
        self._attr_is_on = False
        self.async_write_ha_state()

    def _set_kelvin(self, kelvin: int) -> None:
        kind = self._kind
        if kind.xy_beyond_range and not kind.min_kelvin <= kelvin <= kind.max_kelvin:
            self._set(ColorMode.XY, _planckian_xy(kelvin))
            return
        kelvin = max(kind.min_kelvin, min(kind.max_kelvin, kelvin))
        if kind.coarse:
            span = kind.max_kelvin - kind.min_kelvin
            kelvin = kind.min_kelvin + round(round((kelvin - kind.min_kelvin) / span * 1000) * span / 1000)
        self._set(ColorMode.COLOR_TEMP, kelvin)

    def _set(self, mode: ColorMode, value) -> None:
        """Shows `value` in `mode`, as the bulb reports it."""
        if mode == ColorMode.XY and self._kind.rounds_xy:
            value = (round(value[0], 4), round(value[1], 4))
        self._attr_color_mode = mode
        if mode == ColorMode.COLOR_TEMP:
            self._attr_color_temp_kelvin = int(value)
        elif mode == ColorMode.HS:
            self._attr_hs_color = tuple(value)
        elif mode == ColorMode.RGB:
            self._attr_rgb_color = tuple(value)
        elif mode == ColorMode.RGBW:
            self._attr_rgbw_color = tuple(value)
        elif mode == ColorMode.RGBWW:
            self._attr_rgbww_color = tuple(value)
        elif mode == ColorMode.XY:
            self._attr_xy_color = tuple(value)


def _planckian_xy(kelvin: float) -> tuple[float, float]:
    """A white's true xy (Kim et al.'s cubic fit, 1667-25000K), as a bulb
    shows it: unlike HA's Kelvin->hs, which isn't colorimetric."""
    t = min(max(kelvin, 1667), 25000)
    if t <= 4000:
        x = -0.2661239e9 / t**3 - 0.2343589e6 / t**2 + 0.8776956e3 / t + 0.179910
    else:
        x = -3.0258469e9 / t**3 + 2.1070379e6 / t**2 + 0.2226347e3 / t + 0.240390
    if t <= 2222:
        y = -1.1063814 * x**3 - 1.34811020 * x**2 + 2.18555832 * x - 0.20219683
    elif t <= 4000:
        y = -0.9549476 * x**3 - 1.37418593 * x**2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x**3 - 5.87338670 * x**2 + 3.75112997 * x - 0.37001483
    return x, y
