"""Brightness/colour-temperature schedule maths. Timestamps are unix
seconds; boundaries are today's, computed in coordinator.py."""

import math

# The one HA import: a colour conversion isn't worth reimplementing.
from homeassistant.util.color import color_temperature_to_rgb

# The only place these numbers are literals.
DEFAULT_MORNING_BRIGHTNESS = 255
DEFAULT_DAY_BRIGHTNESS = 255
DEFAULT_EVENING_BRIGHTNESS = 180
DEFAULT_NIGHT_BRIGHTNESS = 80
DEFAULT_MORNING_KELVIN = 6667
DEFAULT_DAY_KELVIN = DEFAULT_MORNING_KELVIN
DEFAULT_EVENING_KELVIN = 3200
DEFAULT_NIGHT_KELVIN = 2700

# Minutes before each phase ends to start easing to the next phase's
# value, named for the phase the transition runs in. 0 is a hard cut.
# Day's Kelvin default is longer than any Day, so it spans the whole phase.
DEFAULT_MORNING_BRIGHTNESS_TRANSITION = 60
DEFAULT_MORNING_KELVIN_TRANSITION = 60
DEFAULT_DAY_BRIGHTNESS_TRANSITION = 65
DEFAULT_DAY_KELVIN_TRANSITION = 1440
DEFAULT_EVENING_BRIGHTNESS_TRANSITION = 60
DEFAULT_EVENING_KELVIN_TRANSITION = 60
DEFAULT_NIGHT_BRIGHTNESS_TRANSITION = 30
DEFAULT_NIGHT_KELVIN_TRANSITION = 30

# Keyed like coordinator.py's CURVE_KEYS.
DEFAULT_CURVE_VALUES = {
    "morning_brightness": DEFAULT_MORNING_BRIGHTNESS,
    "morning_kelvin": DEFAULT_MORNING_KELVIN,
    "day_brightness": DEFAULT_DAY_BRIGHTNESS,
    "day_kelvin": DEFAULT_DAY_KELVIN,
    "evening_brightness": DEFAULT_EVENING_BRIGHTNESS,
    "evening_kelvin": DEFAULT_EVENING_KELVIN,
    "night_brightness": DEFAULT_NIGHT_BRIGHTNESS,
    "night_kelvin": DEFAULT_NIGHT_KELVIN,
    "morning_brightness_transition": DEFAULT_MORNING_BRIGHTNESS_TRANSITION,
    "morning_kelvin_transition": DEFAULT_MORNING_KELVIN_TRANSITION,
    "day_brightness_transition": DEFAULT_DAY_BRIGHTNESS_TRANSITION,
    "day_kelvin_transition": DEFAULT_DAY_KELVIN_TRANSITION,
    "evening_brightness_transition": DEFAULT_EVENING_BRIGHTNESS_TRANSITION,
    "evening_kelvin_transition": DEFAULT_EVENING_KELVIN_TRANSITION,
    "night_brightness_transition": DEFAULT_NIGHT_BRIGHTNESS_TRANSITION,
    "night_kelvin_transition": DEFAULT_NIGHT_KELVIN_TRANSITION,
}

# Hours of day, used to seed new time entities and the docs playground.
DEFAULT_SCHEDULE_HOURS = {
    "morning": 6,
    "day": 8,
    "evening_earliest": 17,
    "evening_latest": 20,
    "night": 22,
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def kelvin_to_rgb(kelvin: float) -> tuple:
    """Kelvin -> RGB via HA's conversion, rounded half-up to match the card's
    Math.round. (round() would pass today's tests, since no integer Kelvin
    lands on .5 - keep it anyway.)

    HA clamps input to 1000-40000K, reachable through compute_curve."""
    return tuple(int(math.floor(c + 0.5)) for c in color_temperature_to_rgb(kelvin))


def phase_at(t: float, morning_ts: float, day_start_ts: float, evening_ts: float, night_ts: float) -> str:
    """Which phase an instant falls in, given today's boundaries."""
    if t < morning_ts:
        return "Night"
    if t < day_start_ts:
        return "Morning"
    if t < evening_ts:
        return "Day"
    if t < night_ts:
        return "Evening"
    return "Night"


PHASE_ORDER = ("Morning", "Day", "Evening", "Night")


def phase_marks(morning_ts: float, day_start_ts: float, evening_ts: float, night_ts: float) -> list:
    """Which phases occur today, and when each actually starts, as
    [(name, start_ts), ...].

    Boundaries can be set out of order. phase_at() cascades through
    `t < boundary` tests, so a phase can be unreachable (Morning at 10:00,
    Day at 08:00: never Morning), and the next phase then starts at the
    later boundary. Each phase starts at the running max of the boundaries
    up to its own. Night gets a mark only for its return, and only if some
    other phase happens at all.

    For anything drawing boundaries directly, like the card's labels."""
    raw = (morning_ts, day_start_ts, evening_ts, night_ts)

    effective_starts = []
    running = None
    for ts in raw:
        running = ts if running is None else max(running, ts)
        effective_starts.append(running)

    marks = []
    for i, name in enumerate(PHASE_ORDER[:-1]):
        # Squeezed out by the next phase starting no later than it does.
        if effective_starts[i] < effective_starts[i + 1]:
            marks.append((name, effective_starts[i]))

    # Night last, and only if some other phase happens.
    if marks:
        marks.append(("Night", effective_starts[-1]))
    return marks


SECONDS_PER_DAY = 86400

# Night wraps to Morning, so it's the only span crossing midnight.
_NEXT_PHASE = {"Morning": "Day", "Day": "Evening", "Evening": "Night", "Night": "Morning"}


def _phase_span(day_phase: str, now_ts: float, boundaries: dict) -> tuple:
    """(start, end) of the phase's own span. Night is one span crossing
    midnight, starting either yesterday or today."""
    if day_phase == "Morning":
        return boundaries["morning"], boundaries["day"]
    if day_phase == "Day":
        return boundaries["day"], boundaries["evening"]
    if day_phase == "Evening":
        return boundaries["evening"], boundaries["night"]
    if now_ts >= boundaries["night"]:
        return boundaries["night"], boundaries["morning"] + SECONDS_PER_DAY
    return boundaries["night"] - SECONDS_PER_DAY, boundaries["morning"]


def _value_at(
    day_phase: str,
    now_ts: float,
    boundaries: dict,
    values: dict,
    duration_minutes: float,
) -> float:
    """This phase's value now, easing toward the next phase's over the last
    `duration_minutes` of the phase, so the next value arrives exactly at
    the boundary. The duration is clamped to the phase.

    day_phase can be an override, so now_ts may be outside the phase's
    span. The factor is clamped so it can't extrapolate, and strictly past
    the span it returns the phase's own value rather than the next phase's."""
    own = values[day_phase]
    span_start, span_end = _phase_span(day_phase, now_ts, boundaries)
    duration = min(max(duration_minutes, 0) * 60, max(span_end - span_start, 0))
    if duration <= 0:
        return own
    ramp_start = span_end - duration
    if now_ts <= ramp_start or now_ts > span_end:
        return own
    t = _clamp((now_ts - ramp_start) / duration, 0, 1)
    return own + (values[_NEXT_PHASE[day_phase]] - own) * t


def brightness_for_phase(
    day_phase: str,
    now_ts: float,
    morning_ts: float,
    day_start_ts: float,
    evening_ts: float,
    night_ts: float,
    *,
    morning_brightness: int = DEFAULT_MORNING_BRIGHTNESS,
    day_brightness: int = DEFAULT_DAY_BRIGHTNESS,
    evening_brightness: int = DEFAULT_EVENING_BRIGHTNESS,
    night_brightness: int = DEFAULT_NIGHT_BRIGHTNESS,
    morning_brightness_transition: float = DEFAULT_MORNING_BRIGHTNESS_TRANSITION,
    day_brightness_transition: float = DEFAULT_DAY_BRIGHTNESS_TRANSITION,
    evening_brightness_transition: float = DEFAULT_EVENING_BRIGHTNESS_TRANSITION,
    night_brightness_transition: float = DEFAULT_NIGHT_BRIGHTNESS_TRANSITION,
) -> int:
    """Target brightness (0-255) for the given phase/instant."""
    return round(
        _value_at(
            day_phase,
            now_ts,
            {"morning": morning_ts, "day": day_start_ts, "evening": evening_ts, "night": night_ts},
            {
                "Morning": morning_brightness,
                "Day": day_brightness,
                "Evening": evening_brightness,
                "Night": night_brightness,
            },
            {
                "Morning": morning_brightness_transition,
                "Day": day_brightness_transition,
                "Evening": evening_brightness_transition,
                "Night": night_brightness_transition,
            }[day_phase],
        )
    )


def kelvin_for_phase(
    day_phase: str,
    now_ts: float,
    morning_ts: float,
    day_start_ts: float,
    evening_ts: float,
    night_ts: float,
    *,
    morning_kelvin: int = DEFAULT_MORNING_KELVIN,
    day_kelvin: int = DEFAULT_DAY_KELVIN,
    evening_kelvin: int = DEFAULT_EVENING_KELVIN,
    night_kelvin: int = DEFAULT_NIGHT_KELVIN,
    morning_kelvin_transition: float = DEFAULT_MORNING_KELVIN_TRANSITION,
    day_kelvin_transition: float = DEFAULT_DAY_KELVIN_TRANSITION,
    evening_kelvin_transition: float = DEFAULT_EVENING_KELVIN_TRANSITION,
    night_kelvin_transition: float = DEFAULT_NIGHT_KELVIN_TRANSITION,
) -> int:
    """Target colour temperature (Kelvin) for the given phase/instant."""
    return round(
        _value_at(
            day_phase,
            now_ts,
            {"morning": morning_ts, "day": day_start_ts, "evening": evening_ts, "night": night_ts},
            {
                "Morning": morning_kelvin,
                "Day": day_kelvin,
                "Evening": evening_kelvin,
                "Night": night_kelvin,
            },
            {
                "Morning": morning_kelvin_transition,
                "Day": day_kelvin_transition,
                "Evening": evening_kelvin_transition,
                "Night": night_kelvin_transition,
            }[day_phase],
        )
    )


def targets_for_phase(
    day_phase: str,
    now_ts: float,
    evening_ts: float,
    day_start_ts: float,
    night_ts: float,
    morning_ts: float,
    **curve_values,
) -> dict:
    """brightness/kelvin/rgb_color for a phase. Takes the phase rather than
    computing it, so the caller can substitute an override. Curve values
    pass through as kwargs; unknown keys raise."""
    boundaries = (now_ts, morning_ts, day_start_ts, evening_ts, night_ts)
    brightness = brightness_for_phase(
        day_phase, *boundaries, **{k: v for k, v in curve_values.items() if "brightness" in k}
    )
    kelvin = kelvin_for_phase(
        day_phase, *boundaries, **{k: v for k, v in curve_values.items() if "kelvin" in k}
    )
    return {
        "brightness": brightness,
        "kelvin": kelvin,
        "rgb_color": kelvin_to_rgb(kelvin),
    }
