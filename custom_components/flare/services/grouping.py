"""Turns "these entities, this target" into the minimal set of
light.turn_on/turn_off calls. Pure: HA access is injected through an
EntityLookup."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable, Optional

from ..const import DEFAULT_OVERRIDE_BRIGHTNESS_TOLERANCE, DEFAULT_OVERRIDE_COLOR_TEMP_TOLERANCE, is_reachable
from ..tracking.matching import (
    DEFAULT_BRIGHTNESS_TOLERANCE,
    DEFAULT_COLOR_TEMP_TOLERANCE,
    DEFAULT_RGB_COLOR_TOLERANCE,
    Tolerance,
    shows,
)
from ..tracking.override_protection import classify_state, is_blocked
from .two_step import TWO_STEP_LABEL_ID, model_matches

if TYPE_CHECKING:
    from homeassistant.core import State

_RGB_COLOR_MODES = {"rgb", "rgbw", "rgbww", "hs", "xy"}

# light.turn_on silently clamps to this, so an unclamped target would
# never read as reached and be re-sent every tick.
MAX_BRIGHTNESS = 255


@dataclass
class EntityLookup:
    """HA state/registry access, injected so this module never sees `hass`."""

    state: Callable[[str], Optional["State"]]
    device_id: Callable[[str], Optional[str]]
    labels: Callable[[str], list]
    # (None, None) for an entity with no device.
    manufacturer_model: Callable[[str], tuple[Optional[str], Optional[str]]]
    # The light's claims, or None if it has none or the caller tracks nothing - see claims.py.
    claims: Callable[[str], Optional[dict]]

    def is_state(self, entity_id: str, value: str) -> bool:
        s = self.state(entity_id)
        return s is not None and s.state == value

    def state_attr(self, entity_id: str, attr: str) -> object:
        s = self.state(entity_id)
        return s.attributes.get(attr) if s is not None else None

    def reachable(self, entity_id: str) -> bool:
        """False for anything HA knows it can't reach."""
        return is_reachable(self.state(entity_id))

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
        brightness_tolerance: int = DEFAULT_BRIGHTNESS_TOLERANCE,
        color_temp_tolerance: int = DEFAULT_COLOR_TEMP_TOLERANCE,
        rgb_color_tolerance: int = DEFAULT_RGB_COLOR_TOLERANCE,
        brightness_percent: float = DEFAULT_OVERRIDE_BRIGHTNESS_TOLERANCE,
        color_temp_mireds: float = DEFAULT_OVERRIDE_COLOR_TEMP_TOLERANCE,
    ) -> bool:
        """True if something other than the caller's own writes has touched this
        light since. force bypasses it."""
        status, _matched_via = classify_state(
            self.state(entity_id),
            self.claims(entity_id),
            brightness_tolerance,
            color_temp_tolerance,
            rgb_color_tolerance,
            brightness_percent,
            color_temp_mireds,
        )
        return is_blocked(status, force)

    def supports_rgb(self, entity_id: str) -> bool:
        """True if the entity supports a mode rgb_color works with."""
        modes = self.state_attr(entity_id, "supported_color_modes") or []
        return bool(set(modes) & _RGB_COLOR_MODES)


@dataclass
class Group:
    """One brightness bucket's commands. `target` (and `target_rgb` for the
    *_rgb lists) is what the group's lights are sent, and so what was tested
    against and what a write's claim records - one dict, so they can't differ."""

    brightness: int
    target: dict = field(default_factory=dict)
    target_rgb: Optional[dict] = None
    needing_off: list = field(default_factory=list)
    combined: list = field(default_factory=list)
    two_step: list = field(default_factory=list)
    combined_rgb: list = field(default_factory=list)
    two_step_rgb: list = field(default_factory=list)
    # On and already showing the target, so nothing is sent to them.
    already_set: list = field(default_factory=list)


def target_brightness(entity_id: str, brightness_levels: dict, brightness: Optional[int]) -> Optional[int]:
    """The brightness `entity_id` is sent: 0 for off, None for hands off.

    A light without a level gets `brightness`. Either way 0 is off, as it is
    for light.turn_on, and anything else is clamped to 1-MAX_BRIGHTNESS.
    null/false ("something else owns this") are matched by identity,
    because `False == 0`."""
    if entity_id in brightness_levels:
        value = brightness_levels[entity_id]
        if value is None or value is False:
            return None
    else:
        value = brightness
    value = float(value)
    return 0 if value <= 0 else min(max(round(value), 1), MAX_BRIGHTNESS)


def _bucket_by_brightness(entities: list, brightness_levels: dict, brightness: Optional[int]) -> dict:
    """Buckets entities by the brightness they're sent, so each bucket shares
    one command. Hands-off lights are left out."""
    buckets: dict = {}
    for e in entities:
        target = target_brightness(e, brightness_levels, brightness)
        if target is not None:
            buckets.setdefault(target, []).append(e)
    return buckets


def build_groups(
    entities: list,
    brightness_levels: dict,
    sensor_brightness: Optional[int],
    sensor_color_temp_kelvin: int,
    lookup: EntityLookup,
    brightness_tolerance: int = DEFAULT_BRIGHTNESS_TOLERANCE,
    color_temp_tolerance: int = DEFAULT_COLOR_TEMP_TOLERANCE,
    two_step_label: str = TWO_STEP_LABEL_ID,
    two_step_model_patterns: Iterable[str] = (),
    prefer_rgb_color: bool = False,
    rgb_color: Optional[tuple] = None,
    rgb_color_tolerance: int = DEFAULT_RGB_COLOR_TOLERANCE,
    force: bool = False,
    min_brightness_change: float = 0,
    min_color_temp_change: float = 0,
    brightness_percent: float = DEFAULT_OVERRIDE_BRIGHTNESS_TOLERANCE,
    color_temp_mireds: float = DEFAULT_OVERRIDE_COLOR_TEMP_TOLERANCE,
) -> list:
    """What needs commanding for `entities`, bucketed by the brightness each
    is sent. Each Group is an off-group (brightness 0, `needing_off`) or an
    update-group holding whatever isn't already close enough.

    Close enough is within tolerance, or within the minimum change worth
    sending: `min_brightness_change` percent of the target brightness, and
    `min_color_temp_change` mireds. These only decide what's sent; override
    protection still matches on the tolerances.

    prefer_rgb_color + rgb_color route RGB-capable lights into the *_rgb
    lists. A light is two-step if it carries two_step_label or its model
    matches two_step_model_patterns. force bypasses override protection.
    brightness_percent and color_temp_mireds are override matching's own
    tolerances, the Settings entry's options."""
    use_rgb = prefer_rgb_color and rgb_color is not None
    # Override matching's own tolerances say whose change it was, not what's
    # worth sending, so only the minimum change widens this.
    close_enough = Tolerance(
        brightness_tolerance,
        color_temp_tolerance,
        rgb_color_tolerance,
        min_brightness_change,
        min_color_temp_change,
        brightness_percent=0,
        color_temp_mireds=0,
    )

    def writable(lights: list) -> list:
        return [
            e
            for e in lights
            if lookup.reachable(e)
            and not lookup.externally_set(
                e,
                force,
                brightness_tolerance,
                color_temp_tolerance,
                rgb_color_tolerance,
                brightness_percent,
                color_temp_mireds,
            )
        ]

    def route(lights: list, target: Optional[dict]) -> tuple[list, list, list]:
        """(already set, two-step, combined) for lights sent `target`."""
        candidates = writable(lights)
        already = [e for e in candidates if _already_set(e, target, lookup, close_enough)]
        needing = [e for e in candidates if e not in already]
        two_step = [
            e
            for e in needing
            if two_step_label in lookup.tags(e) or lookup.matches_two_step_pattern(e, two_step_model_patterns)
        ]
        return already, two_step, [e for e in needing if e not in two_step]

    groups = []
    for brightness, group_entities in _bucket_by_brightness(entities, brightness_levels, sensor_brightness).items():
        if brightness <= 0:
            group = Group(brightness=brightness, target={"state": "off"})
            group.needing_off = [e for e in writable(group_entities) if not lookup.is_state(e, "off")]
            groups.append(group)
            continue

        group = Group(
            brightness=brightness,
            target={"brightness": brightness, "color_temp_kelvin": sensor_color_temp_kelvin},
            target_rgb={"brightness": brightness, "rgb_color": list(rgb_color)} if use_rgb else None,
        )
        if use_rgb:
            rgb_entities = [e for e in group_entities if lookup.supports_rgb(e)]
            temp_entities = [e for e in group_entities if e not in rgb_entities]
        else:
            rgb_entities, temp_entities = [], group_entities

        already, group.two_step, group.combined = route(temp_entities, group.target)
        already_rgb, group.two_step_rgb, group.combined_rgb = route(rgb_entities, group.target_rgb)
        group.already_set = already + already_rgb
        groups.append(group)

    return groups


def _already_set(entity_id: str, target: dict, lookup: EntityLookup, tolerance: Tolerance) -> bool:
    """On and close enough not to send - see matching.py."""
    state = lookup.state(entity_id)
    return state is not None and state.state == "on" and shows(state.attributes, target, tolerance)
