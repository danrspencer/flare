"""Override protection's decision table: given one light's claims and live
state, is it ours to write? Pure; the caller supplies the claims for
whatever zone it named. grouping.py's externally_set(), sensor.py's status
and claims_check all go through classify_state(), so they can't disagree.

Each light has two claims: `observed`, a state we've seen and can safely
write over, and `latest`, our most recent write, not yet seen landing.
See claims.py's module docstring."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, TypedDict

# HA's own conversions, so they match what devices actually report.
from homeassistant.util import dt as dt_util
from homeassistant.util.color import color_temperature_kelvin_to_mired as _kelvin_to_mired
from homeassistant.util.color import color_temperature_to_rgb as _kelvin_to_rgb

if TYPE_CHECKING:
    from homeassistant.core import State

DEFAULT_BRIGHTNESS_TOLERANCE = 2
DEFAULT_COLOR_TEMP_TOLERANCE = 10
DEFAULT_RGB_COLOR_TOLERANCE = 10


class _ContextClaim(TypedDict):
    context_id: str
    # A two-step write's brightness-step context; either step landing counts
    # as ours. None for a single combined write.
    secondary_context_id: Optional[str]
    # ISO 8601, or None for the first-write baseline.
    recorded_at: Optional[str]
    # What this write asked for, or None if it isn't one of our writes.
    target: Optional[dict]


class _WriteRecord(TypedDict):
    observed: Optional[_ContextClaim]
    latest: Optional[_ContextClaim]
    # ISO 8601 last write, for pruning only.
    last_seen: Optional[str]


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _context_matches(claim: Optional[dict], current_context: Optional[str]) -> bool:
    """True if `current_context` is either of the claim's context ids."""
    if claim is None:
        return False
    return current_context == claim["context_id"] or (
        claim.get("secondary_context_id") is not None and current_context == claim["secondary_context_id"]
    )


def _color_temp_matches(current_kelvin: int, target_kelvin: int, tolerance_kelvin: int) -> bool:
    """Within tolerance, or both floor to the same mired - the unit Zigbee
    bulbs actually use, so they're indistinguishable to the device. A flat
    Kelvin tolerance can't cover it: one mired is ~5K at 2700K but ~20K
    at 4500K. E.g. 4373K floors to mired 228, which reads back as 4385K."""
    if abs(current_kelvin - target_kelvin) <= tolerance_kelvin:
        return True
    return _kelvin_to_mired(current_kelvin) == _kelvin_to_mired(target_kelvin)


def _color_temp_matches_rgb(target_kelvin: int, current_rgb, tolerance: int) -> bool:
    """True if a Kelvin target and a live rgb_color are the same colour. HA
    reports color_temp_kelvin as None outside COLOR_TEMP mode, so a bulb in
    xy/rgb mode can only match this way."""
    if not isinstance(current_rgb, (list, tuple)) or len(current_rgb) != 3:
        return False
    target_rgb = _kelvin_to_rgb(target_kelvin)
    return all(abs(a - b) <= tolerance for a, b in zip(current_rgb, target_rgb))


def _clamp_kelvin(target_kelvin: int, min_kelvin, max_kelvin) -> int:
    """The target, clamped to the bulb's advertised range (0 = unknown)."""
    lo = _as_int(min_kelvin, 0)
    hi = _as_int(max_kelvin, 0)
    if lo > 0:
        target_kelvin = max(target_kelvin, lo)
    if hi > 0:
        target_kelvin = min(target_kelvin, hi)
    return target_kelvin


def target_matches_values(
    target: Optional[dict],
    current_brightness,
    current_color_temp_kelvin,
    current_rgb_color,
    brightness_tolerance: int = DEFAULT_BRIGHTNESS_TOLERANCE,
    color_temp_tolerance: int = DEFAULT_COLOR_TEMP_TOLERANCE,
    rgb_color_tolerance: int = DEFAULT_RGB_COLOR_TOLERANCE,
    min_color_temp_kelvin=None,
    max_color_temp_kelvin=None,
) -> bool:
    """Whether live values still match what a claim asked for, even though
    its context doesn't. A falsy target never matches.

    min/max_color_temp_kelvin: the bulb's advertised range, so a bulb
    parked at its ceiling still matches a target beyond it."""
    if not target:
        return False
    target_brightness = target.get("brightness")
    if target_brightness is None:
        return False
    if abs(_as_int(current_brightness, -999) - target_brightness) > brightness_tolerance:
        return False
    target_rgb = target.get("rgb_color")
    if target_rgb is not None:
        return (
            isinstance(current_rgb_color, (list, tuple))
            and len(current_rgb_color) == 3
            and all(abs(a - b) <= rgb_color_tolerance for a, b in zip(current_rgb_color, target_rgb))
        )
    target_color_temp = target.get("color_temp_kelvin")
    if target_color_temp is None:
        return False
    current_kelvin = _as_int(current_color_temp_kelvin, -999)
    if _color_temp_matches(current_kelvin, target_color_temp, color_temp_tolerance):
        return True
    # A bulb in xy/rgb mode has no color_temp_kelvin to compare.
    if _color_temp_matches_rgb(target_color_temp, current_rgb_color, rgb_color_tolerance):
        return True
    reachable = _clamp_kelvin(target_color_temp, min_color_temp_kelvin, max_color_temp_kelvin)
    return reachable != target_color_temp and _color_temp_matches(current_kelvin, reachable, color_temp_tolerance)


def _asked_for_off(claim: Optional[dict]) -> bool:
    """True if this claim was a turn-off ({"state": "off"})."""
    if not claim:
        return False
    target = claim.get("target") or {}
    return target.get("state") == "off"


def classify(
    is_on: bool,
    observed: Optional[dict],
    latest: Optional[dict],
    current_context: Optional[str],
    current_brightness=None,
    current_color_temp_kelvin=None,
    current_rgb_color=None,
    brightness_tolerance: int = DEFAULT_BRIGHTNESS_TOLERANCE,
    color_temp_tolerance: int = DEFAULT_COLOR_TEMP_TOLERANCE,
    rgb_color_tolerance: int = DEFAULT_RGB_COLOR_TOLERANCE,
    min_color_temp_kelvin=None,
    max_color_temp_kelvin=None,
) -> tuple[str, Optional[str]]:
    """The decision table. Returns `(status, matched_via)`.

    - "off": not on, and no claim. An off light with a claim is judged
      against it like any other state.
    - "untracked": no claim, or only an unverified `latest` that doesn't
      match. Free to manage. (A dropped first-ever write looks like this
      too, until an `observed` exists.)
    - "controlled": the live context matches a claim, or the live values
      match what one asked for. Values matter because HA forgets a write's
      context after 5s, so a slow device echoes under a new one, and
      because a dropped `latest` leaves the light showing `observed`.
    - "overridden": an `observed` claim exists and neither claim matches.

    `matched_via` ("latest-context", "latest-value", "observed-context",
    "observed-value", or None) is diagnostic only."""
    if observed is None and latest is None:
        return ("untracked" if is_on else "off"), None
    if _context_matches(latest, current_context):
        return "controlled", "latest-context"
    if _context_matches(observed, current_context):
        return "controlled", "observed-context"
    if not is_on:
        # An off light matches only a claim that asked for off.
        if _asked_for_off(latest):
            return "controlled", "latest-value"
        if _asked_for_off(observed):
            return "controlled", "observed-value"
        if observed is None:
            return "untracked", None
        return "overridden", None
    if observed is None:
        return "untracked", None
    if latest is not None and target_matches_values(
        latest.get("target"),
        current_brightness,
        current_color_temp_kelvin,
        current_rgb_color,
        brightness_tolerance,
        color_temp_tolerance,
        rgb_color_tolerance,
        min_color_temp_kelvin,
        max_color_temp_kelvin,
    ):
        return "controlled", "latest-value"
    if target_matches_values(
        observed.get("target"),
        current_brightness,
        current_color_temp_kelvin,
        current_rgb_color,
        brightness_tolerance,
        color_temp_tolerance,
        rgb_color_tolerance,
        min_color_temp_kelvin,
        max_color_temp_kelvin,
    ):
        return "controlled", "observed-value"
    return "overridden", None


# How long after a light comes back online its reports are still the bulb
# settling (Zigbee2MQTT sends the attributes some seconds after the state).
RECONNECT_SETTLE = timedelta(seconds=30)


def classify_state(
    state: Optional["State"],
    record: Optional[_WriteRecord],
    brightness_tolerance: int = DEFAULT_BRIGHTNESS_TOLERANCE,
    color_temp_tolerance: int = DEFAULT_COLOR_TEMP_TOLERANCE,
    rgb_color_tolerance: int = DEFAULT_RGB_COLOR_TOLERANCE,
    reconnected_at: Optional[datetime] = None,
) -> tuple[str, Optional[str]]:
    """classify() for a live HA state and its claim record (None if
    untracked). "unavailable" for a light HA can't reach or doesn't know,
    before any claim is consulted.

    A light still showing what it came back online as (last updated within
    RECONNECT_SETTLE of `reconnected_at`) that FLARE wrote to after it came
    back is "untracked" rather than "overridden": the command was lost as
    the bulb booted, nobody changed the light, so FLARE sends it again.
    Without this it stays overridden at its power-on default. Only writes
    after the reconnect count, so a light someone changed before it dropped
    out stays theirs; and claims.py forgets the reconnect once a write from
    FLARE lands, so a change after that is an override as usual.

    Otherwise a light that came back online less than RECONNECT_SETTLE ago
    and doesn't match is "settling": its first reports are often stale, so
    it isn't called overridden yet, but it's blocked as one."""
    if state is None or state.state in ("unavailable", "unknown"):
        return "unavailable", None
    status, matched_via = _classify_live(
        state, record or {}, brightness_tolerance, color_temp_tolerance, rgb_color_tolerance
    )
    if status != "overridden" or reconnected_at is None:
        return status, matched_via
    settles_at = reconnected_at + RECONNECT_SETTLE
    if state.last_updated <= settles_at and _written_since(record or {}, reconnected_at):
        return "untracked", None
    if dt_util.utcnow() < settles_at:
        return "settling", None
    return status, matched_via


def _written_since(record: _WriteRecord, when: datetime) -> bool:
    """Whether FLARE's latest write was recorded at or after `when`."""
    recorded = (record.get("latest") or {}).get("recorded_at")
    if not recorded:
        return False
    try:
        return datetime.fromisoformat(recorded) >= when
    except (TypeError, ValueError):
        return False


def _classify_live(state, record, brightness_tolerance, color_temp_tolerance, rgb_color_tolerance):
    attributes = state.attributes
    return classify(
        state.state == "on",
        record.get("observed"),
        record.get("latest"),
        state.context.id,
        attributes.get("brightness"),
        attributes.get("color_temp_kelvin"),
        attributes.get("rgb_color"),
        brightness_tolerance,
        color_temp_tolerance,
        rgb_color_tolerance,
        attributes.get("min_color_temp_kelvin"),
        attributes.get("max_color_temp_kelvin"),
    )


def is_blocked(status: str, force: bool = False) -> bool:
    """classify()'s status as a yes/no. There's no owner check: callers naming
    the same zone share its claims. `force` bypasses."""
    if force:
        return False
    return status in ("overridden", "settling")
