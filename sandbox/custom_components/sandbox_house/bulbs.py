"""The kinds of bulb a room can have: a plain colour-temperature bulb, and
odd ones behaving like awkward real bulbs."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.light import ColorMode


@dataclass(frozen=True)
class Kind:
    """How a bulb behaves. HA's light.turn_on converts what it's sent into
    the first of `modes` that can take it, as it does for a real bulb."""

    label: str
    modes: frozenset[ColorMode]
    # The range it obeys, and the range it advertises (the same unless it lies).
    min_kelvin: int = 2200
    max_kelvin: int = 6500
    advertised_min_kelvin: int | None = None
    advertised_max_kelvin: int | None = None
    # Asked for a Kelvin beyond its range, it shows that white in xy, as many
    # Zigbee bulbs do.
    xy_beyond_range: bool = False
    # Reports xy to 4 decimal places, as Zigbee does.
    rounds_xy: bool = False
    # Reports brightness in whole percent and Kelvin in 1000 steps of its
    # range, as many Tuya devices do.
    coarse: bool = False


KINDS = {
    "plain": Kind("Bulb", frozenset({ColorMode.COLOR_TEMP})),
    "rgb_strip": Kind("RGB strip", frozenset({ColorMode.RGB})),
    "rgbw_strip": Kind("RGBW strip", frozenset({ColorMode.RGBW})),
    "rgbww_strip": Kind("RGBWW strip", frozenset({ColorMode.RGBWW}), min_kelvin=2700),
    "hs_bulb": Kind("HS bulb", frozenset({ColorMode.HS})),
    "xy_bulb": Kind("XY bulb", frozenset({ColorMode.XY}), rounds_xy=True),
    "colour_bulb": Kind(
        "Colour bulb", frozenset({ColorMode.COLOR_TEMP, ColorMode.XY}), xy_beyond_range=True, rounds_xy=True
    ),
    "lying_spot": Kind("Lying spot", frozenset({ColorMode.COLOR_TEMP}), advertised_max_kelvin=4000),
    "coarse_bulb": Kind("Coarse bulb", frozenset({ColorMode.COLOR_TEMP}), coarse=True),
    "dimmer": Kind("Dimmer", frozenset({ColorMode.BRIGHTNESS})),
    "on_off": Kind("On-off", frozenset({ColorMode.ONOFF})),
}
