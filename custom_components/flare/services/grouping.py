"""Turns "these entities, this target" into the minimal set of
light.turn_on/turn_off calls. Pure: HA access is injected through an
EntityLookup."""

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from ..tracking.override_protection import _color_temp_matches, classify, is_blocked
from .two_step import TWO_STEP_LABEL_ID, model_matches

_RGB_COLOR_MODES = {"rgb", "rgbw", "rgbww", "hs", "xy"}

# light.turn_on silently clamps to this, so an unclamped target would
# never read as reached and be re-sent every tick.
MAX_BRIGHTNESS = 255


@dataclass
class EntityLookup:
    """HA state/registry access, injected so this module never sees `hass`."""

    is_state: Callable[[str, str], bool]
    state_attr: Callable[[str, str], object]
    device_id: Callable[[str], Optional[str]]
    labels: Callable[[str], list]
    # (None, None) for an entity with no device.
    manufacturer_model: Callable[[str], tuple[Optional[str], Optional[str]]]
    context_id: Callable[[str], Optional[str]]
    # The two claims - see write_tracking.py's module docstring.
    observed_context_id: Callable[[str], Optional[str]]
    latest_context_id: Callable[[str], Optional[str]]
    # What each claim asked for, or None if it isn't one of our writes.
    # Lets externally_set() recognise our own write echoed back under a new
    # context.
    latest_target: Callable[[str], Optional[dict]]
    observed_target: Callable[[str], Optional[dict]]
    # A two-step write's brightness-step context, or None.
    latest_secondary_context_id: Callable[[str], Optional[str]]
    observed_secondary_context_id: Callable[[str], Optional[str]]

    def reachable(self, entity_id: str) -> bool:
        """False for anything HA knows it can't reach."""
        return not self.is_state(entity_id, "unavailable") and not self.is_state(entity_id, "unknown")

    def tags(self, entity_id: str) -> list:
        """Labels on the entity itself plus its device (if any)."""
        did = self.device_id(entity_id)
        return self.labels(entity_id) + (self.labels(did) if did else [])

    def matches_two_step_pattern(self, entity_id: str, patterns: Iterable[str]) -> bool:
        """True if the device's "<manufacturer> <model>" matches a pattern."""
        manufacturer, model = self.manufacturer_model(entity_id)
        return model_matches(manufacturer, model, patterns)

    def externally_set(
        self,
        entity_id: str,
        force: bool = False,
        brightness_tolerance: int = 2,
        color_temp_tolerance: int = 10,
        rgb_color_tolerance: int = 10,
    ) -> bool:
        """True if something other than the caller's own writes has touched this
        light since. An adapter over override_protection.classify()/is_blocked(),
        which hold the decision table. force bypasses it."""
        observed_ctx = self.observed_context_id(entity_id)
        observed = (
            {
                "context_id": observed_ctx,
                "secondary_context_id": self.observed_secondary_context_id(entity_id),
                "target": self.observed_target(entity_id),
            }
            if observed_ctx is not None
            else None
        )
        latest_ctx = self.latest_context_id(entity_id)
        latest = (
            {
                "context_id": latest_ctx,
                "secondary_context_id": self.latest_secondary_context_id(entity_id),
                "target": self.latest_target(entity_id),
            }
            if latest_ctx is not None
            else None
        )

        status, _matched_via = classify(
            self.is_state(entity_id, "on"),
            observed,
            latest,
            self.context_id(entity_id),
            self.state_attr(entity_id, "brightness"),
            self.state_attr(entity_id, "color_temp_kelvin"),
            self.state_attr(entity_id, "rgb_color"),
            brightness_tolerance,
            color_temp_tolerance,
            rgb_color_tolerance,
            self.state_attr(entity_id, "min_color_temp_kelvin"),
            self.state_attr(entity_id, "max_color_temp_kelvin"),
        )
        return is_blocked(status, force)

    def supports_rgb(self, entity_id: str) -> bool:
        """True if the entity supports a mode rgb_color works with."""
        modes = self.state_attr(entity_id, "supported_color_modes") or []
        return bool(set(modes) & _RGB_COLOR_MODES)


@dataclass
class Group:
    multiplier: float
    brightness: int
    needing_off: list = field(default_factory=list)
    combined: list = field(default_factory=list)
    two_step: list = field(default_factory=list)
    combined_rgb: list = field(default_factory=list)
    two_step_rgb: list = field(default_factory=list)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp_color_temp_kelvin(entity_id: str, target_kelvin: int, lookup: EntityLookup) -> int:
    """The target Kelvin, clamped to the entity's advertised range.

    HA doesn't clamp color_temp_kelvin for a native COLOR_TEMP light; the
    bulb does, and settles at its ceiling. Only the comparison is clamped,
    not what's sent, so a group can share one command. Advertised ranges
    aren't always honest, so callers accept the raw target too."""
    lo = _as_int(lookup.state_attr(entity_id, "min_color_temp_kelvin"), 0)
    hi = _as_int(lookup.state_attr(entity_id, "max_color_temp_kelvin"), 0)
    if lo > 0:
        target_kelvin = max(target_kelvin, lo)
    if hi > 0:
        target_kelvin = min(target_kelvin, hi)
    return target_kelvin


def _bucket_by_multiplier(entities: list, brightness_multipliers: dict) -> dict:
    """Buckets entities by multiplier so each bucket shares one command.
    null/false ("something else owns this") are left out."""
    buckets: dict = {}
    for e in entities:
        m = brightness_multipliers.get(e, 1)
        if m is None or m is False:
            continue
        buckets.setdefault(m, []).append(e)
    return buckets


def build_groups(
    entities: list,
    brightness_multipliers: dict,
    sensor_brightness: int,
    sensor_color_temp_kelvin: int,
    lookup: EntityLookup,
    brightness_tolerance: int = 2,
    color_temp_tolerance: int = 10,
    two_step_label: str = TWO_STEP_LABEL_ID,
    two_step_model_patterns: Iterable[str] = (),
    prefer_rgb_color: bool = False,
    rgb_color: Optional[tuple] = None,
    rgb_color_tolerance: int = 10,
    force: bool = False,
    min_brightness_change: float = 0,
    min_color_temp_change: float = 0,
) -> list:
    """What needs commanding for `entities`, bucketed by brightness
    multiplier. Each Group is an off-group (multiplier <= 0, `needing_off`)
    or an update-group holding whatever isn't already close enough.

    Close enough is within tolerance, or within the minimum change worth
    sending: `min_brightness_change` percent of the target brightness, and
    `min_color_temp_change` mireds. These only decide what's sent; override
    protection still matches on the tolerances.

    prefer_rgb_color + rgb_color route RGB-capable lights into the *_rgb
    lists. A light is two-step if it carries two_step_label or its model
    matches two_step_model_patterns. force bypasses override protection."""
    use_rgb = prefer_rgb_color and rgb_color is not None
    groups = []
    for multiplier, group_entities in _bucket_by_multiplier(entities, brightness_multipliers).items():
        m = float(multiplier)
        # Floored at 1 (0 is the multiplier's way to say off) and capped at
        # MAX_BRIGHTNESS.
        brightness = 0 if m == 0 else min(max(round(sensor_brightness * m), 1), MAX_BRIGHTNESS)
        group = Group(multiplier=multiplier, brightness=brightness)

        if brightness <= 0:
            group.needing_off = [
                e
                for e in group_entities
                if lookup.reachable(e)
                and not lookup.is_state(e, "off")
                and not lookup.externally_set(e, force, brightness_tolerance, color_temp_tolerance, rgb_color_tolerance)
            ]
            groups.append(group)
            continue

        if use_rgb:
            rgb_entities = [e for e in group_entities if lookup.supports_rgb(e)]
            temp_entities = [e for e in group_entities if e not in rgb_entities]
        else:
            rgb_entities, temp_entities = [], group_entities

        needing_update = [
            e
            for e in temp_entities
            if lookup.reachable(e)
            and not lookup.externally_set(e, force, brightness_tolerance, color_temp_tolerance, rgb_color_tolerance)
            and not _already_set(
                e,
                brightness,
                sensor_color_temp_kelvin,
                lookup,
                brightness_tolerance,
                color_temp_tolerance,
                min_brightness_change,
                min_color_temp_change,
            )
        ]
        group.two_step = [
            e
            for e in needing_update
            if two_step_label in lookup.tags(e) or lookup.matches_two_step_pattern(e, two_step_model_patterns)
        ]
        group.combined = [e for e in needing_update if e not in group.two_step]

        needing_update_rgb = [
            e
            for e in rgb_entities
            if lookup.reachable(e)
            and not lookup.externally_set(e, force, brightness_tolerance, color_temp_tolerance, rgb_color_tolerance)
            and not _already_set_rgb(
                e, brightness, rgb_color, lookup, brightness_tolerance, rgb_color_tolerance, min_brightness_change
            )
        ]
        group.two_step_rgb = [
            e
            for e in needing_update_rgb
            if two_step_label in lookup.tags(e) or lookup.matches_two_step_pattern(e, two_step_model_patterns)
        ]
        group.combined_rgb = [e for e in needing_update_rgb if e not in group.two_step_rgb]

        groups.append(group)

    return groups


def _brightness_close(
    entity_id: str, target_brightness: int, lookup: EntityLookup, brightness_tolerance: int, min_change: float
) -> bool:
    """Within tolerance, or within `min_change` percent of the target."""
    current_brightness = _as_int(lookup.state_attr(entity_id, "brightness"), -999)
    allowed = max(brightness_tolerance, target_brightness * min_change / 100)
    return abs(current_brightness - target_brightness) <= allowed


def _within_mireds(current_kelvin: int, target_kelvin: int, min_change: float) -> bool:
    """Mireds, because equal steps in them look roughly equal across the
    range, where a flat Kelvin gap doesn't."""
    if current_kelvin <= 0 or target_kelvin <= 0:
        return False
    return abs(1_000_000 / current_kelvin - 1_000_000 / target_kelvin) <= min_change


def _color_temp_close(current_kelvin: int, target_kelvin: int, tolerance: int, min_change: float) -> bool:
    return _color_temp_matches(current_kelvin, target_kelvin, tolerance) or _within_mireds(
        current_kelvin, target_kelvin, min_change
    )


def _already_set(
    entity_id: str,
    target_brightness: int,
    target_color_temp_kelvin: int,
    lookup: EntityLookup,
    brightness_tolerance: int,
    color_temp_tolerance: int,
    min_brightness_change: float = 0,
    min_color_temp_change: float = 0,
) -> bool:
    """Close enough not to send: within tolerance, since bulbs round-trip
    values a point or two off, or within the minimum change worth sending.
    Kelvin also matches when both floor to the same mired."""
    if not lookup.is_state(entity_id, "on"):
        return False
    if not _brightness_close(entity_id, target_brightness, lookup, brightness_tolerance, min_brightness_change):
        return False
    current_color_temp = _as_int(lookup.state_attr(entity_id, "color_temp_kelvin"), -999)
    if _color_temp_close(current_color_temp, target_color_temp_kelvin, color_temp_tolerance, min_color_temp_change):
        return True
    # Also accept the target clamped to the bulb's range - see
    # clamp_color_temp_kelvin.
    reachable_target = clamp_color_temp_kelvin(entity_id, target_color_temp_kelvin, lookup)
    return reachable_target != target_color_temp_kelvin and _color_temp_close(
        current_color_temp, reachable_target, color_temp_tolerance, min_color_temp_change
    )


def _already_set_rgb(
    entity_id: str,
    target_brightness: int,
    target_rgb: tuple,
    lookup: EntityLookup,
    brightness_tolerance: int,
    rgb_color_tolerance: int,
    min_brightness_change: float = 0,
) -> bool:
    """_already_set for RGB, per channel. A missing rgb_color counts as not
    close."""
    if not lookup.is_state(entity_id, "on"):
        return False
    if not _brightness_close(entity_id, target_brightness, lookup, brightness_tolerance, min_brightness_change):
        return False
    current_rgb = lookup.state_attr(entity_id, "rgb_color")
    return (
        isinstance(current_rgb, (list, tuple))
        and len(current_rgb) == 3
        and all(abs(_as_int(c, -999) - int(t)) <= rgb_color_tolerance for c, t in zip(current_rgb, target_rgb))
    )
