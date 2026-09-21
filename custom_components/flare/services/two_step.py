"""
Matching primitives for two-step transitions: some bulbs can't take
brightness and colour temperature in one command - sent together, they
either snap or drop one of the two. grouping.py routes a matching light
into two sequential half-length calls instead (see build_groups' two_step
/two_step_rgb buckets), decided by EntityLookup.matches_two_step_pattern()
- a light's device "<manufacturer> <model>" checked against the pattern
list here - OR'd with the `no_combined_transition` label as a manual
escape hatch for anything a pattern doesn't (yet) cover. Pure logic, no
Home Assistant imports - the registry access lives in services/handlers.py and is
injected, same split as curve.py/grouping.py/scenes.py.

DEFAULT_TWO_STEP_MODEL_PATTERNS is the shipped list, and it is also
literally what the options field is pre-populated with (see
config_flow.py) - there is no hidden second list layered underneath.
Whatever is in that field IS the list, so a user can remove a shipped
pattern they disagree with as easily as they can add one, and what they
see in the box is exactly what routing uses.

The trade-off that buys: once a user saves the field, they own it, and
a later release adding a newly discovered bulb to the shipped defaults
will not reach them - their saved copy wins. That is the cost of "what
you see is what runs"; contributing a pattern upstream still helps every
install that hasn't customised the field. Higher-stakes than it sounds:
a pattern list now drives live dispatch directly, not just a repair
suggestion, so an overly broad or wrong pattern has an immediate effect.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Iterable

TWO_STEP_LABEL_ID = "no_combined_transition"

# Case-insensitive glob patterns matched against "<manufacturer> <model>".
#
# Deliberately narrow: every entry here should be a bulb someone has
# actually observed misbehaving, not a guess. A pattern that's too broad
# is worse than a missing one - it routes those bulbs into two-step
# transitions live, which makes them transition *worse* (two calls when
# one would have been fine) with no repair or confirmation step in the way.
#
# Adding to this list is the intended way to contribute a newly found
# bulb: one line here, and every install picks it up on its next update.
DEFAULT_TWO_STEP_MODEL_PATTERNS: tuple[str, ...] = (
    # IKEA TRADFRI - the original case this whole code path exists for.
    # Covers the GU10/E27/E14 spectrum bulbs, which all share the prefix.
    "*TRADFRI bulb*",
)


def parse_patterns(raw: str | Iterable[str] | None) -> list[str]:
    """Turns the options-flow text field into a pattern list.

    Accepts a newline- or comma-separated string (what the multiline text
    selector hands back) or an already-split iterable, and drops blanks
    and surrounding whitespace. Anything falsy yields an empty list
    rather than raising - a misconfigured options field should quietly
    fall back to the shipped defaults, never break setup.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        parts: Iterable[str] = raw.replace(",", "\n").splitlines()
    else:
        parts = raw
    return [p.strip() for p in parts if isinstance(p, str) and p.strip()]


def model_matches(manufacturer: str | None, model: str | None, patterns: Iterable[str]) -> bool:
    """True if this device looks like a known two-step bulb.

    Matched against "<manufacturer> <model>" so a pattern can pin either
    or both ("IKEA*", "*TRADFRI bulb*"). Case-insensitive, because
    manufacturer strings are wildly inconsistent between integrations
    for the same physical device.
    """
    haystack = f"{manufacturer or ''} {model or ''}".strip().lower()
    if not haystack:
        return False
    return any(fnmatch(haystack, pattern.strip().lower()) for pattern in patterns if pattern.strip())
