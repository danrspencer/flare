"""Override protection's decision table: given one light's claims and live
state, is it ours to write? Pure; the caller supplies the claims for
whatever zone it named. grouping.py's externally_set(), sensor.py's status
and claims_check all go through classify_state(), so they can't disagree.

Each light has two claims: `observed`, a state we've seen and can safely
write over, and `latest`, our most recent write, not yet seen landing.
See claims.py's module docstring."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, TypedDict

from homeassistant.util import dt as dt_util

from .matching import (
    DEFAULT_BRIGHTNESS_TOLERANCE,
    DEFAULT_COLOR_TEMP_TOLERANCE,
    DEFAULT_RGB_COLOR_TOLERANCE,
    Tolerance,
    shows,
)

if TYPE_CHECKING:
    from homeassistant.core import State


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


def _context_matches(claim: Optional[dict], current_context: Optional[str]) -> bool:
    """True if `current_context` is either of the claim's context ids."""
    if claim is None:
        return False
    return current_context == claim["context_id"] or (
        claim.get("secondary_context_id") is not None and current_context == claim["secondary_context_id"]
    )


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
    attributes: Mapping = {},
    tolerance: Tolerance = Tolerance(),
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
    if latest is not None and shows(attributes, latest.get("target"), tolerance):
        return "controlled", "latest-value"
    if shows(attributes, observed.get("target"), tolerance):
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
    status, matched_via = classify(
        state.state == "on",
        (record or {}).get("observed"),
        (record or {}).get("latest"),
        state.context.id,
        state.attributes,
        Tolerance(brightness_tolerance, color_temp_tolerance, rgb_color_tolerance),
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


def is_blocked(status: str, force: bool = False) -> bool:
    """classify()'s status as a yes/no. There's no owner check: callers naming
    the same zone share its claims. `force` bypasses."""
    if force:
        return False
    return disagrees(status)
