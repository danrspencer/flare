"""Whether a light shows a target: the one place a light's reported values
are compared with what was asked for. Override protection asks it (is this
still what FLARE set?) and so does grouping (does this need sending?), so
the two can't drift apart.

A target is what a write asked for: `{"brightness", "color_temp_kelvin"}`
or `{"brightness", "rgb_color"}`. (`{"state": "off"}` is an off-claim,
which override protection handles before values come into it.)

Reading a light:

- Brightness is `brightness`, 0-255.
- Colour temperature is `color_temp_kelvin`, which HA gives only in
  COLOR_TEMP mode. In a colour mode (hs, xy, rgb...) HA gives `xy_color`,
  with `rgb_color` and `hs_color` worked out from the bulb's report, and a
  white there is read as Kelvin from `xy_color` with HA's
  `color_xy_to_temperature`, if it's within MAX_WHITE_DUV of the Planckian
  locus. Never by comparing RGB: HA's Kelvin->RGB and xy->RGB conversions
  disagree by ~13 in red at 6500K, so a bulb showing exactly what was
  asked would read as something else. A Zigbee bulb asked for more than its
  advertised range often reports in xy.
- RGB is `rgb_color`, compared only against an RGB target.

Comparing, for a Kelvin target:

- Within the Kelvin tolerance, or the same mired: Zigbee bulbs speak
  mireds and HA floors both conversions, so 4373K reads back as 4385K.
- Against the target as asked, or clamped to the bulb's advertised range.
  Advertised ranges aren't always honest (spots advertising 4000K show
  6575K), while an honest bulb parks at its ceiling, so either is accepted.

The minimum changes (`Tolerance.min_brightness_change`, percent of the
target, and `min_color_temp_change`, mireds) widen the match. Only grouping
sets them: they decide what's worth sending. Override protection never
does, or a hand-set light near the curve would read as FLARE's."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional

from homeassistant.util.color import color_temperature_kelvin_to_mired as _kelvin_to_mired
from homeassistant.util.color import color_xy_to_temperature as _xy_to_kelvin

DEFAULT_BRIGHTNESS_TOLERANCE = 2
DEFAULT_COLOR_TEMP_TOLERANCE = 10
DEFAULT_RGB_COLOR_TOLERANCE = 10

# How far a reported colour can sit from the line of whites (Duv, in CIE
# 1960 uv) and still count as a colour temperature. Coloured light sits far
# beyond it: pink ~0.05, green ~0.15.
MAX_WHITE_DUV = 0.02


@dataclass(frozen=True)
class Tolerance:
    brightness: int = DEFAULT_BRIGHTNESS_TOLERANCE
    color_temp: int = DEFAULT_COLOR_TEMP_TOLERANCE  # Kelvin
    rgb_color: int = DEFAULT_RGB_COLOR_TOLERANCE  # per channel
    min_brightness_change: float = 0  # percent of the target
    min_color_temp_change: float = 0  # mireds


def shows(attributes: Mapping, target: Optional[Mapping], tolerance: Tolerance = Tolerance()) -> bool:
    """Whether a light reporting `attributes` shows `target`. A target
    without a brightness and a colour never matches."""
    if not target or target.get("brightness") is None:
        return False
    if not _brightness_matches(attributes.get("brightness"), target["brightness"], tolerance):
        return False
    if target.get("rgb_color") is not None:
        return _rgb_matches(attributes.get("rgb_color"), target["rgb_color"], tolerance.rgb_color)
    if target.get("color_temp_kelvin") is None:
        return False
    current = reported_kelvin(attributes)
    if current is None:
        return False
    asked = int(target["color_temp_kelvin"])
    reachable = _clamp(asked, attributes.get("min_color_temp_kelvin"), attributes.get("max_color_temp_kelvin"))
    return _kelvin_matches(current, asked, tolerance) or (
        reachable != asked and _kelvin_matches(current, reachable, tolerance)
    )


def shown(attributes: Mapping) -> dict:
    """What a light shows, as a target: its brightness and Kelvin, or its
    rgb_color if it isn't showing a white."""
    target = {"brightness": attributes.get("brightness")}
    kelvin = reported_kelvin(attributes)
    if kelvin is not None:
        target["color_temp_kelvin"] = kelvin
    elif attributes.get("rgb_color") is not None:
        target["rgb_color"] = list(attributes["rgb_color"])
    return target


def reported_kelvin(attributes: Mapping) -> Optional[int]:
    """The colour temperature a light reports: `color_temp_kelvin`, or a
    white's `xy_color` read as Kelvin. None if there's neither."""
    kelvin = _as_int(attributes.get("color_temp_kelvin"))
    if kelvin is not None:
        return kelvin
    xy = attributes.get("xy_color")
    if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        return None
    try:
        x, y = float(xy[0]), float(xy[1])
        kelvin = _xy_to_kelvin(x, y)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return kelvin if _duv(x, y, kelvin) <= MAX_WHITE_DUV else None


def _brightness_matches(current, asked: int, tolerance: Tolerance) -> bool:
    current = _as_int(current)
    if current is None:
        return False
    allowed = max(tolerance.brightness, asked * tolerance.min_brightness_change / 100)
    return abs(current - asked) <= allowed


def _kelvin_matches(current: int, asked: int, tolerance: Tolerance) -> bool:
    if current <= 0 or asked <= 0:
        return False
    if abs(current - asked) <= tolerance.color_temp:
        return True
    if _kelvin_to_mired(current) == _kelvin_to_mired(asked):
        return True
    return abs(1_000_000 / current - 1_000_000 / asked) <= tolerance.min_color_temp_change


def _rgb_matches(current, asked, tolerance: int) -> bool:
    if not isinstance(current, (list, tuple)) or len(current) != 3:
        return False
    try:
        return all(abs(int(c) - int(a)) <= tolerance for c, a in zip(current, asked))
    except (TypeError, ValueError):
        return False


def _clamp(kelvin: int, min_kelvin, max_kelvin) -> int:
    """`kelvin` within the bulb's advertised range, where it gives one."""
    lo, hi = _as_int(min_kelvin) or 0, _as_int(max_kelvin) or 0
    if lo > 0:
        kelvin = max(kelvin, lo)
    if hi > 0:
        kelvin = min(kelvin, hi)
    return kelvin


def _duv(x: float, y: float, kelvin: int) -> float:
    """Distance from the Planckian locus at `kelvin`, in CIE 1960 uv."""
    u, v = _xy_to_uv(x, y)
    locus_u, locus_v = _xy_to_uv(*_planckian_xy(min(max(kelvin, 1667), 25000)))
    return ((u - locus_u) ** 2 + (v - locus_v) ** 2) ** 0.5


def _planckian_xy(kelvin: float) -> tuple[float, float]:
    """The Planckian locus' xy: Kim et al.'s cubic fit, 1667-25000K."""
    t = kelvin
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


def _xy_to_uv(x: float, y: float) -> tuple[float, float]:
    d = -2 * x + 12 * y + 3
    return 4 * x / d, 6 * y / d


def _as_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
