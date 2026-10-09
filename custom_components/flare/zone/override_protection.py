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
from homeassistant.util.color import color_xy_to_temperature as _xy_to_kelvin

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


class _WriteRecord(TypedDict, total=False):
    observed: Optional[_ContextClaim]
    latest: Optional[_ContextClaim]
    # ISO 8601 last write, for pruning only.
    last_seen: Optional[str]
    # ISO 8601: when the light first stopped matching its claims, kept by
    # claims.py. Absent while it matches.
    mismatch_since: Optional[str]


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


# How far a reported colour can sit from the line of whites (Duv, in CIE
# 1960 uv) and still count as a colour temperature. Coloured light sits far
# beyond it: pink ~0.05, green ~0.15.
MAX_WHITE_DUV = 0.02


def reported_kelvin(attributes) -> Optional[int]:
    """The colour temperature a light reports. HA gives color_temp_kelvin only
    in COLOR_TEMP mode; in a colour mode (a Zigbee bulb asked for more than its
    advertised range often reports xy) it's read from xy_color, if that's a
    white. None if there's neither."""
    kelvin = attributes.get("color_temp_kelvin")
    if kelvin is not None:
        return _as_int(kelvin, None)
    xy = attributes.get("xy_color")
    if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        return None
    try:
        kelvin = _xy_to_kelvin(float(xy[0]), float(xy[1]))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return kelvin if _duv(xy[0], xy[1], kelvin) <= MAX_WHITE_DUV else None


def _duv(x: float, y: float, kelvin: int) -> float:
    """Distance from the Planckian locus at `kelvin`, in CIE 1960 uv."""
    locus_x, locus_y = _planckian_xy(min(max(kelvin, 1667), 25000))
    u, v = _xy_to_uv(x, y)
    locus_u, locus_v = _xy_to_uv(locus_x, locus_y)
    return ((u - locus_u) ** 2 + (v - locus_v) ** 2) ** 0.5


def _planckian_xy(kelvin: float) -> tuple[float, float]:
    """The Planckian locus' xy (Kim et al.'s cubic fit, 1667-25000K)."""
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

# How long a light can disagree with its claims before it counts as
# overridden: long enough for FLARE's own write to land, a bulb back online
# to report properly, or a room switched off light by light to go dark.
MISMATCH_GRACE = timedelta(seconds=30)


def classify_state(
    state: Optional["State"],
    record: Optional[_WriteRecord],
    brightness_tolerance: int = DEFAULT_BRIGHTNESS_TOLERANCE,
    color_temp_tolerance: int = DEFAULT_COLOR_TEMP_TOLERANCE,
    rgb_color_tolerance: int = DEFAULT_RGB_COLOR_TOLERANCE,
    reconnected_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
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

    Otherwise a light that doesn't match is "mismatched" until its record's
    `mismatch_since` (kept by claims.py) is MISMATCH_GRACE old, and only
    then "overridden": most mismatches are FLARE's own write still landing
    or a bulb reporting late. A mismatched light is blocked like an
    overridden one, so a real change is never written over meanwhile."""
    if state is None or state.state in ("unavailable", "unknown"):
        return "unavailable", None
    status, matched_via = _classify_live(
        state, record or {}, brightness_tolerance, color_temp_tolerance, rgb_color_tolerance
    )
    if status != "overridden":
        return status, matched_via
    if (
        reconnected_at is not None
        and state.last_updated <= reconnected_at + RECONNECT_SETTLE
        and _written_since(record or {}, reconnected_at)
    ):
        return "untracked", None
    since = _parse((record or {}).get("mismatch_since"))
    if since is None or (now or dt_util.utcnow()) < since + MISMATCH_GRACE:
        return "mismatched", None
    return status, matched_via


def disagrees(status: str) -> bool:
    """Whether a status means the light doesn't match its claims."""
    return status in ("mismatched", "overridden")


def _parse(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


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
        reported_kelvin(attributes),
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
    return disagrees(status)
