"""What counts as a bare turn-on: one asking for nothing but "on"."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# A transition says how, not what, so a turn-on carrying only one is still bare.
_IGNORED = frozenset({"transition"})


def is_bare_turn_on(kwargs: Mapping[str, Any]) -> bool:
    """True when a light.turn_on asks for no brightness, colour or effect."""
    return not set(kwargs) - _IGNORED
