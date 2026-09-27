"""Which bulbs need two-step transitions: they can't take brightness and
colour temperature in one command. Matched on "<manufacturer> <model>",
or the `no_combined_transition` label as a manual override.

The options field is pre-filled with DEFAULT_TWO_STEP_MODEL_PATTERNS and
is the whole list, so a saved field no longer picks up new defaults."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Iterable

TWO_STEP_LABEL_ID = "no_combined_transition"

# Case-insensitive globs against "<manufacturer> <model>". Keep them
# narrow: only bulbs actually seen misbehaving, since a match makes a
# bulb that didn't need it transition worse.
DEFAULT_TWO_STEP_MODEL_PATTERNS: tuple[str, ...] = (
    # IKEA TRADFRI GU10/E27/E14 spectrum bulbs.
    "*TRADFRI bulb*",
)


def parse_patterns(raw: str | Iterable[str] | None) -> list[str]:
    """The options field (newline- or comma-separated) as a pattern list.
    Never raises: a bad field falls back to the defaults."""
    if not raw:
        return []
    if isinstance(raw, str):
        parts: Iterable[str] = raw.replace(",", "\n").splitlines()
    else:
        parts = raw
    return [p.strip() for p in parts if isinstance(p, str) and p.strip()]


def model_matches(manufacturer: str | None, model: str | None, patterns: Iterable[str]) -> bool:
    """True if "<manufacturer> <model>" matches a pattern. Case-insensitive,
    since integrations report manufacturers inconsistently."""
    haystack = f"{manufacturer or ''} {model or ''}".strip().lower()
    if not haystack:
        return False
    return any(fnmatch(haystack, pattern.strip().lower()) for pattern in patterns if pattern.strip())
