"""
FLARE's services.

Eight of them, registered by the Tracking entry - every one is about
which lights are being driven and by whom, and needs the claim registry
that entry owns:

- `apply_lighting` - the only one that switches lights on; wraps
  grouping.py's planner and dispatches light.turn_on/turn_off.
- `turn_off` - the turn-off counterpart: records, then switches off.
- `compute_lighting_groups` / `compute_curve` / `compute_scene_coverage`
  - pure planners that return data and touch nothing.
- `claims_check` / `claims_record` / `claims_clear` - override protection
  exposed standalone (see write_tracking.py and override_protection.py).

Everything here is an adapter between Home Assistant and the logic that
decides things: it reads real state and registries into the plain
lookups grouping.py and scenes.py are written against (_build_lookup,
_build_scene_lookup), calls them, and issues the resulting service calls.
The decisions themselves live in curve.py, grouping.py, scenes.py and
override_protection.py, none of which is handed a `hass`.

The handlers are closures inside async_setup_services because each needs
the entry and its ClaimRegistry, which only exist per tracking entry.
Field contracts are in services.yaml (visible in Developer Tools ->
Actions) and docs/advanced/reference.md.
"""

from __future__ import annotations

import asyncio

# A plain `import time` is fine here. It would NOT be in the package's own
# __init__.py: this package has a time.py (the HA `time` platform), and
# importing that submodule rebinds `time` on the package, which is
# __init__.py's own global namespace - so every later time.time() there
# raised AttributeError against the wrong module. A submodule's globals are
# its own, so this one is not clobbered.
import time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..const import CONF_TWO_STEP_MODELS, DOMAIN
from ..schedule.coordinator import CURVE_KEYS
from ..schedule.curve import phase_at, targets_for_phase
from .grouping import EntityLookup, Group, build_groups
from ..tracking.override_protection import classify, is_blocked
from .scenes import SceneLookup, compute_scene_coverage
from .two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS, TWO_STEP_LABEL_ID, parse_patterns
from ..tracking.write_tracking import ClaimRegistry

COMPUTE_LIGHTING_GROUPS_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Optional("brightness_multipliers", default=dict): dict,
        vol.Required("brightness"): vol.Coerce(int),
        vol.Required("color_temp_kelvin"): vol.Coerce(int),
        vol.Optional("brightness_tolerance", default=2): vol.Coerce(int),
        vol.Optional("color_temp_tolerance", default=10): vol.Coerce(int),
        vol.Optional("two_step_label", default=TWO_STEP_LABEL_ID): cv.string,
        vol.Optional("prefer_rgb_color", default=False): cv.boolean,
        # vol.Any(None, ...) rather than a bare vol.All(...) - a caller
        # templating this from a sensor attribute that may not exist
        # (e.g. the blueprint's own adaptive_sensor, for a "bring your
        # own sensor" entity that doesn't populate rgb_color) renders an
        # explicit None, not an omitted key. A bare vol.All([...],
        # vol.Length(...)) rejects None outright as "not a list" -
        # confirmed live as a real gap, not hypothetical, once this
        # exact call shape was worked through for the blueprint change.
        vol.Optional("rgb_color"): vol.Any(None, vol.All([vol.Coerce(int)], vol.Length(min=3, max=3))),
        vol.Optional("rgb_color_tolerance", default=10): vol.Coerce(int),
        vol.Optional("force", default=False): cv.boolean,
        # None (the default) means "write, but track nothing" - this
        # call's light(s) get no claim and nothing is excluded as
        # already externally-set. vol.Any(None, ...), same reasoning as
        # rgb_color above: the blueprint renders an explicit Jinja None
        # when it can't resolve a scope, not an omitted key.
        vol.Optional("tracking_device_id"): vol.Any(None, cv.string),
    }
)

COMPUTE_CURVE_SCHEMA = vol.Schema(
    {
        vol.Required("morning"): vol.Coerce(float),
        vol.Required("day"): vol.Coerce(float),
        vol.Required("evening"): vol.Coerce(float),
        vol.Required("night"): vol.Coerce(float),
        vol.Optional("at"): vol.Coerce(float),
        # Same eight curve fields a sensor's number.* entities expose
        # (see number.py), built from the same CURVE_KEYS (coordinator.py)
        # rather than listing the names again - left unset,
        # targets_for_phase's own defaults apply, matching this
        # service's original behaviour.
        **{vol.Optional(key): vol.Coerce(int) for key in CURVE_KEYS},
    }
)

COMPUTE_SCENE_COVERAGE_SCHEMA = vol.Schema(
    {
        # Required, not vol.Optional: this service answers a question
        # about one specific scene - with no candidate scene, the caller
        # already knows the answer (nothing's covered, everything falls
        # to their own default) without asking, the same reasoning as
        # CLAIMS_CHECK_SCHEMA/CLAIMS_RECORD_SCHEMA/CLAIMS_CLEAR_SCHEMA
        # below for tracking_device_id.
        vol.Required("scene_entity_id"): cv.entity_id,
        vol.Required("scope_entities"): [cv.entity_id],
        vol.Required("target_entities"): [cv.entity_id],
    }
)

APPLY_LIGHTING_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Optional("brightness_multipliers", default=dict): dict,
        vol.Required("brightness"): vol.Coerce(int),
        vol.Required("color_temp_kelvin"): vol.Coerce(int),
        vol.Required("transition"): vol.Coerce(float),
        vol.Optional("brightness_tolerance", default=2): vol.Coerce(int),
        vol.Optional("color_temp_tolerance", default=10): vol.Coerce(int),
        vol.Optional("two_step_label", default=TWO_STEP_LABEL_ID): cv.string,
        vol.Optional("prefer_rgb_color", default=False): cv.boolean,
        # See COMPUTE_LIGHTING_GROUPS_SCHEMA's own rgb_color comment for
        # why vol.Any(None, ...) rather than a bare vol.All(...).
        vol.Optional("rgb_color"): vol.Any(None, vol.All([vol.Coerce(int)], vol.Length(min=3, max=3))),
        vol.Optional("rgb_color_tolerance", default=10): vol.Coerce(int),
        vol.Optional("force", default=False): cv.boolean,
        # None (the default) means "write, but track nothing" - this
        # call's light(s) get no claim and nothing is excluded as
        # already externally-set. vol.Any(None, ...), same reasoning as
        # rgb_color above: the blueprint renders an explicit Jinja None
        # when it can't resolve a scope, not an omitted key.
        vol.Optional("tracking_device_id"): vol.Any(None, cv.string),
    }
)

TURN_OFF_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Optional("transition", default=0): vol.Coerce(float),
        # Optional, same as apply_lighting's: None (or omitted) turns the
        # lights off without tracking anything, and the blueprint renders
        # an explicit Jinja None when it can't resolve a scope.
        vol.Optional("tracking_device_id"): vol.Any(None, cv.string),
    }
)

# These three (claims_check/claims_record/claims_clear - prefixed so
# they sort and group together in Developer Tools -> Actions) exist for
# no reason other than to read or write tracking claims - unlike
# apply_lighting/compute_lighting_groups, which still do something
# useful (dispatch/plan lights) with no scope at all, there is no
# meaningful reason to call any of these three without one. Required,
# not vol.Any(None, ...): a caller with nothing to name shouldn't be
# calling these services in the first place, and a schema-level failure
# is a much louder signal than the previous "always empty, silently" was.
CLAIMS_CHECK_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Required("tracking_device_id"): cv.string,
        vol.Optional("brightness_tolerance", default=2): vol.Coerce(int),
        vol.Optional("color_temp_tolerance", default=10): vol.Coerce(int),
        vol.Optional("rgb_color_tolerance", default=10): vol.Coerce(int),
    }
)

CLAIMS_RECORD_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Required("tracking_device_id"): cv.string,
        vol.Optional("targets", default=dict): dict,
    }
)

CLAIMS_CLEAR_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Required("tracking_device_id"): cv.string,
    }
)


def _build_lookup(hass: HomeAssistant, tracker: ClaimRegistry, subentry_id: str | None) -> EntityLookup:
    """Adapts real HA state/registries to the plain EntityLookup
    interface grouping.py expects - the only HA-specific piece of this
    integration, everything else is the pure modules doing the work.

    subentry_id is the caller's own resolved scope (see
    resolve_scope_device on the tracker), bound into each claim accessor
    as a closure here - the one place a whole call's scope gets fixed
    once and threaded through every entity it looks up. EntityLookup
    itself stays entity_id-only; it has no notion of scope at all."""

    def is_state(entity_id: str, state: str) -> bool:
        s = hass.states.get(entity_id)
        return s is not None and s.state == state

    def state_attr(entity_id: str, attr: str) -> Any:
        s = hass.states.get(entity_id)
        return s.attributes.get(attr) if s else None

    def device_id(entity_id: str) -> str | None:
        entry = er.async_get(hass).async_get(entity_id)
        return entry.device_id if entry else None

    def manufacturer_model(entity_id: str) -> tuple[str | None, str | None]:
        entity_entry = er.async_get(hass).async_get(entity_id)
        if entity_entry is None or entity_entry.device_id is None:
            return None, None
        device_entry = dr.async_get(hass).async_get(entity_entry.device_id)
        if device_entry is None:
            return None, None
        return device_entry.manufacturer, device_entry.model

    def labels(id_: str | None) -> list:
        # id_ may be an entity_id or a device_id - EntityLookup.tags()
        # calls this with both, mirroring how HA's own `labels()`
        # template global is polymorphic over either.
        if not id_:
            return []
        entity_entry = er.async_get(hass).async_get(id_)
        if entity_entry is not None:
            return list(entity_entry.labels)
        device_entry = dr.async_get(hass).async_get(id_)
        if device_entry is not None:
            return list(device_entry.labels)
        return []

    def context_id(entity_id: str) -> str | None:
        s = hass.states.get(entity_id)
        return s.context.id if s else None

    return EntityLookup(
        is_state=is_state,
        state_attr=state_attr,
        device_id=device_id,
        labels=labels,
        manufacturer_model=manufacturer_model,
        context_id=context_id,
        observed_context_id=lambda eid: tracker.observed_context_id(subentry_id, eid),
        latest_context_id=lambda eid: tracker.latest_context_id(subentry_id, eid),
        latest_target=lambda eid: tracker.latest_target(subentry_id, eid),
        observed_target=lambda eid: tracker.observed_target(subentry_id, eid),
        latest_secondary_context_id=lambda eid: tracker.latest_secondary_context_id(subentry_id, eid),
        observed_secondary_context_id=lambda eid: tracker.observed_secondary_context_id(subentry_id, eid),
    )


def _two_step_model_patterns(entry: ConfigEntry) -> list[str]:
    """Whatever entry.options[CONF_TWO_STEP_MODELS] holds, or the shipped
    defaults if unset/empty - not additive, a saved value replaces the
    defaults outright (see two_step.py's own module docstring for why).
    Read fresh on every call rather than cached, so an options change
    (which reloads the entry anyway) never risks a stale list."""
    configured = parse_patterns(entry.options.get(CONF_TWO_STEP_MODELS))
    return configured or list(DEFAULT_TWO_STEP_MODEL_PATTERNS)


def _build_scene_lookup(hass: HomeAssistant) -> SceneLookup:
    def exists(scene_entity_id: str) -> bool:
        return hass.states.get(scene_entity_id) is not None

    def covered_entities(scene_entity_id: str) -> list:
        s = hass.states.get(scene_entity_id)
        return list(s.attributes.get("entity_id", [])) if s else []

    return SceneLookup(exists=exists, covered_entities=covered_entities)


def _groups_response(groups: list[Group]) -> ServiceResponse:
    return {
        "groups": [
            {
                "multiplier": g.multiplier,
                "brightness": g.brightness,
                "needing_off": g.needing_off,
                "combined": g.combined,
                "two_step": g.two_step,
                "combined_rgb": g.combined_rgb,
                "two_step_rgb": g.two_step_rgb,
            }
            for g in groups
        ]
    }


async def _two_step_turn_on(
    hass: HomeAssistant,
    entity_ids: list,
    brightness: int,
    half_transition: float,
    *,
    brightness_context: Context,
    color_context: Context,
    color_temp_kelvin: int | None = None,
    rgb_color: list | None = None,
) -> None:
    """Brightness-only call, wait, then brightness + colour - for bulbs
    that can't transition both together (no_combined_transition label).
    Works the same for either colour representation; only the second
    call's colour field differs.

    Each step gets its own real Context() rather than sharing one - a
    two-step transition genuinely is two separate light.turn_on calls,
    and forcing them to share a single context.id meant a device
    reporting the brightness-only step on its own (a real, expected
    intermediate state for these bulbs, not an anomaly) did so under a
    context that matched neither the final target nor anything else
    write_tracking.py recognised - indistinguishable from a genuine
    external touch. See write_tracking.py's async_record docstring for
    how either one landing is recognised as ours.

    The caller creates both contexts (parented to the apply_lighting
    call's own, for logbook traceability) and passes them in, rather than
    this function making them and returning their ids. apply_lighting
    records its claims BEFORE dispatching anything, so both ids have to
    exist before either step is sent - this coroutine can be cancelled
    at the sleep below, and an id only known once it returns would be
    lost with it."""
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": entity_ids, "transition": half_transition, "brightness": brightness},
        blocking=True,
        context=brightness_context,
    )
    await asyncio.sleep(half_transition)
    data = {"entity_id": entity_ids, "transition": half_transition, "brightness": brightness}
    if color_temp_kelvin is not None:
        data["color_temp_kelvin"] = color_temp_kelvin
    else:
        data["rgb_color"] = rgb_color
    await hass.services.async_call("light", "turn_on", data, blocking=True, context=color_context)


def async_setup_services(hass: HomeAssistant, entry: ConfigEntry, write_tracker: ClaimRegistry) -> None:
    """Registers the eight services against this tracking entry."""

    async def compute_lighting_groups(call: ServiceCall) -> ServiceResponse:
        """flare.compute_lighting_groups

        Returns: {"groups": [{"multiplier", "brightness", "needing_off",
        "combined", "two_step", "combined_rgb", "two_step_rgb"}, ...]} -
        see services.yaml for field docs.
        """
        rgb_color = call.data.get("rgb_color")
        scope = write_tracker.resolve_scope_device(call.data.get("tracking_device_id"))
        groups = build_groups(
            entities=call.data["entities"],
            brightness_multipliers=call.data["brightness_multipliers"],
            sensor_brightness=call.data["brightness"],
            sensor_color_temp_kelvin=call.data["color_temp_kelvin"],
            lookup=_build_lookup(hass, write_tracker, scope),
            brightness_tolerance=call.data["brightness_tolerance"],
            color_temp_tolerance=call.data["color_temp_tolerance"],
            two_step_label=call.data["two_step_label"],
            two_step_model_patterns=_two_step_model_patterns(entry),
            prefer_rgb_color=call.data["prefer_rgb_color"],
            rgb_color=tuple(rgb_color) if rgb_color else None,
            rgb_color_tolerance=call.data["rgb_color_tolerance"],
            force=call.data["force"],
        )
        return _groups_response(groups)

    async def compute_curve(call: ServiceCall) -> ServiceResponse:
        """flare.compute_curve

        Returns: {"phase", "brightness", "kelvin", "rgb_color"} for the
        given instant (or now) - see services.yaml for field docs.
        """
        at = call.data.get("at", time.time())
        morning, day, evening, night = (
            call.data["morning"],
            call.data["day"],
            call.data["evening"],
            call.data["night"],
        )
        curve_kwargs = {key: call.data[key] for key in CURVE_KEYS if key in call.data}
        phase = phase_at(at, morning, day, evening, night)
        targets = targets_for_phase(phase, at, evening, day, night, morning, **curve_kwargs)
        return {
            "phase": phase,
            "brightness": targets["brightness"],
            "kelvin": targets["kelvin"],
            "rgb_color": list(targets["rgb_color"]),
        }

    async def apply_lighting(call: ServiceCall) -> ServiceResponse:
        """flare.apply_lighting

        Takes brightness/color_temp_kelvin/rgb_color as plain values -
        the same three fields compute_lighting_groups already takes,
        this being the one service in the pair that actually dispatches
        - and turns entities on/off via light.turn_on/turn_off, handling
        reachability, tolerance, externally-set protection, two-step
        transitions, and RGB-vs-colour-temp dispatch internally rather
        than leaving it to the caller. Returns the same {"groups": [...]}
        shape as compute_lighting_groups for introspection, but nothing
        requires capturing it - see services.yaml for field docs.

        tracking_device_id (optional): which FLARE tracking scope this
        write belongs to, for override protection. Omitting it writes
        the light(s) without recording anything - no claim, and nothing
        excluded as already externally-set.

        force (optional, default false): bypasses externally-set
        protection outright for this call. The write is still recorded
        against tracking_device_id if one was given, so a later, non-forced
        call against that same scope correctly recognises it as its own
        rather than finding an orphaned record - the right way to force
        through *and* keep protection working normally afterward. See
        grouping.py's EntityLookup.externally_set() for the full
        semantics of both parameters together.
        """
        force = call.data["force"]
        brightness = call.data["brightness"]
        color_temp_kelvin = call.data["color_temp_kelvin"]
        rgb_color_raw = call.data.get("rgb_color")
        rgb_color = tuple(rgb_color_raw) if rgb_color_raw else None
        scope = write_tracker.resolve_scope_device(call.data.get("tracking_device_id"))
        lookup = _build_lookup(hass, write_tracker, scope)
        groups = build_groups(
            entities=call.data["entities"],
            brightness_multipliers=call.data["brightness_multipliers"],
            sensor_brightness=brightness,
            sensor_color_temp_kelvin=color_temp_kelvin,
            lookup=lookup,
            brightness_tolerance=call.data["brightness_tolerance"],
            color_temp_tolerance=call.data["color_temp_tolerance"],
            two_step_label=call.data["two_step_label"],
            two_step_model_patterns=_two_step_model_patterns(entry),
            prefer_rgb_color=call.data["prefer_rgb_color"],
            rgb_color=rgb_color,
            rgb_color_tolerance=call.data["rgb_color_tolerance"],
            force=force,
        )

        transition = call.data["transition"]
        half_transition = round(transition / 2, 1)
        rgb_color_list = list(rgb_color) if rgb_color is not None else None

        # Every light.turn_on/turn_off call below is given call.context
        # explicitly (rather than left to default to a fresh, unrelated
        # one - see _two_step_turn_on's docstring) so the resulting
        # state's context.id is exactly what write_tracker records below,
        # matching what grouping.py's externally_set() compares against
        # on the next tick.
        written_entities: list = []
        # What each entity's write actually asked for, keyed the same
        # way as written_entities - passed to write_tracker.async_record
        # below so a later context.id mismatch can be checked against
        # what we intended rather than assumed external. An off-command
        # records {"state": "off"}: turning a light off is a write like
        # any other, and without a target of its own there would be
        # nothing to tell "we turned this off" apart from "someone else
        # did" once the write's context expires.
        write_targets: dict = {}
        # Two-step entities get their own pair of contexts (see
        # _two_step_turn_on), not call.context. They are created here,
        # while planning, rather than by the calls that use them: the
        # claims are recorded before anything is dispatched (below), so
        # every id has to exist first. context_id_overrides is the colour
        # step's context (the final, complete state); secondary_context_ids
        # is the brightness step's (see write_tracking.py's async_record).
        # Both stay empty for every non-two-step entity, which keeps
        # using call.context.id alone, unchanged.
        context_id_overrides: dict = {}
        secondary_context_ids: dict = {}
        tasks = []
        for g in groups:
            if g.needing_off:
                written_entities.extend(g.needing_off)
                for e in g.needing_off:
                    write_targets[e] = {"state": "off"}
                tasks.append(
                    hass.services.async_call(
                        "light",
                        "turn_off",
                        {"entity_id": g.needing_off, "transition": transition},
                        blocking=True,
                        context=call.context,
                    )
                )
            if g.combined:
                written_entities.extend(g.combined)
                for e in g.combined:
                    write_targets[e] = {"brightness": g.brightness, "color_temp_kelvin": color_temp_kelvin}
                tasks.append(
                    hass.services.async_call(
                        "light",
                        "turn_on",
                        {
                            "entity_id": g.combined,
                            "transition": transition,
                            "brightness": g.brightness,
                            "color_temp_kelvin": color_temp_kelvin,
                        },
                        blocking=True,
                        context=call.context,
                    )
                )
            if g.combined_rgb:
                written_entities.extend(g.combined_rgb)
                for e in g.combined_rgb:
                    write_targets[e] = {"brightness": g.brightness, "rgb_color": rgb_color_list}
                tasks.append(
                    hass.services.async_call(
                        "light",
                        "turn_on",
                        {
                            "entity_id": g.combined_rgb,
                            "transition": transition,
                            "brightness": g.brightness,
                            "rgb_color": rgb_color_list,
                        },
                        blocking=True,
                        context=call.context,
                    )
                )
            if g.two_step:
                written_entities.extend(g.two_step)
                brightness_context = Context(parent_id=call.context.id)
                color_context = Context(parent_id=call.context.id)
                for e in g.two_step:
                    write_targets[e] = {"brightness": g.brightness, "color_temp_kelvin": color_temp_kelvin}
                    context_id_overrides[e] = color_context.id
                    secondary_context_ids[e] = brightness_context.id
                tasks.append(
                    _two_step_turn_on(
                        hass,
                        g.two_step,
                        g.brightness,
                        half_transition,
                        brightness_context=brightness_context,
                        color_context=color_context,
                        color_temp_kelvin=color_temp_kelvin,
                    )
                )
            if g.two_step_rgb:
                written_entities.extend(g.two_step_rgb)
                brightness_context = Context(parent_id=call.context.id)
                color_context = Context(parent_id=call.context.id)
                for e in g.two_step_rgb:
                    write_targets[e] = {"brightness": g.brightness, "rgb_color": rgb_color_list}
                    context_id_overrides[e] = color_context.id
                    secondary_context_ids[e] = brightness_context.id
                tasks.append(
                    _two_step_turn_on(
                        hass,
                        g.two_step_rgb,
                        g.brightness,
                        half_transition,
                        brightness_context=brightness_context,
                        color_context=color_context,
                        rgb_color=rgb_color_list,
                    )
                )

        # Snapshotted before anything is dispatched, as write_tracker needs
        # it to tell whether the *previous* latest write actually landed,
        # which can only be judged against state as it was before this
        # call's own writes - reading it after would risk comparing a
        # light's context against the very write about to be recorded, if
        # it happened to land synchronously. See write_tracking.py's
        # async_record docstring.
        live_context_before_write = {e: lookup.context_id(e) for e in written_entities}

        # RECORD BEFORE DISPATCH, not after. This used to run once the
        # writes had been awaited, so a run that never got that far - one
        # group's call raising inside the gather, or the blueprint's
        # `mode: restart` cancelling this call while a two-step bulb was
        # asleep between its steps - left lights that HAD changed with no
        # claim to explain it. The next tick then saw a context and values
        # it had never written and called the light overridden, which
        # excludes it until the room goes dark. Nothing errors when that
        # happens; the light just stops following the curve.
        #
        # Recording first is safe because the two-claim model already
        # tolerates an intent that never lands: `latest` is only what we
        # were about to send, and `observed` is replaced solely by a state
        # a bulb was actually seen in (async_record). If nothing arrives,
        # the light still matches its previous, confirmed claim; if only
        # part of it arrives, it matches `latest` via one of the contexts
        # recorded here. It is also free of awaits, so the decision in
        # build_groups() and its record are now one uninterrupted step.
        if written_entities:
            await write_tracker.async_record(
                scope,
                written_entities,
                live_context_before_write,
                call.context.id,
                targets=write_targets,
                secondary_context_ids=secondary_context_ids,
                context_id_overrides=context_id_overrides,
            )

        if tasks:
            await asyncio.gather(*tasks)

        return _groups_response(groups)

    async def turn_off(call: ServiceCall) -> None:
        """flare.turn_off

        Turns `entities` off, and records that as ours so a later
        override check reads it as such rather than as somebody else
        switching the light off. Everything apply_lighting does for a
        turn-off, without needing a brightness or colour target - which is
        why the blueprint's turn-off paths call this rather than
        apply_lighting.

        It exists as ONE operation so a caller can't get the two halves
        wrong. They used to be separate - a bare light.turn_off followed by
        claims_record, with the caller hand-building the `{"state": "off"}`
        target that is this integration's own private encoding of an off
        claim - and both the order and the encoding were the caller's to
        get right. Recording BEFORE dispatching, as apply_lighting does,
        is what keeps a cancelled or failed run from leaving a light that
        did switch off with no claim explaining it (see apply_lighting).

        Unlike apply_lighting this does no override protection: it turns
        off exactly what it is given. Deciding that a room should go dark
        is the caller's call, and it is meant to take lights someone set by
        hand along with everything else. Nothing is filtered for
        reachability either - light.turn_off already ignores what it
        cannot reach, and the claim for such a light is harmless.

        tracking_device_id (optional): which FLARE tracking scope to
        record the turn-off into. Omit it to turn the lights off without
        recording anything.
        """
        entities = call.data["entities"]
        if not entities:
            return
        transition = call.data["transition"]
        scope = write_tracker.resolve_scope_device(call.data.get("tracking_device_id"))
        live_context_before_write = {
            e: (state.context.id if (state := hass.states.get(e)) is not None else None) for e in entities
        }
        await write_tracker.async_record(
            scope,
            entities,
            live_context_before_write,
            call.context.id,
            targets={e: {"state": "off"} for e in entities},
        )
        await hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": entities, "transition": transition},
            blocking=True,
            context=call.context,
        )

    async def claims_check(call: ServiceCall) -> ServiceResponse:
        """flare.claims_check

        For each of `entities`, decides whether a write should currently
        be blocked - the exact same override-protection mechanism
        apply_lighting uses internally (grouping.py's
        EntityLookup.externally_set(), itself a thin wrapper over
        override_protection.classify()/is_blocked()), exposed standalone
        so any caller can ask "should I write this entity" without any
        of this integration's brightness/curve logic at all - see
        docs/advanced/reference.md's "Override protection" section.

        Takes no `force`: forcing is something a *write* does, and as a
        question it has only one possible answer (is_blocked returns
        False for everything when force is set), so asking it is never
        informative.

        Returns: {"results": {entity_id: {"blocked": bool, "status":
        str, "matched_via": str|None, "scope": str}, ...}}.
        "status" is one of "off", "untracked", "controlled",
        "overridden"; "matched_via" is "latest-context",
        "latest-value", "observed-context" or "observed-value" for a
        "controlled" status and null otherwise; "scope" echoes back
        tracking_device_id's own title. See override_protection.classify()
        and services.yaml.

        tracking_device_id (required): which FLARE tracking scope to check
        against - this service exists only to answer questions about
        tracking, so unlike apply_lighting there's nothing useful to do
        without one.
        """
        brightness_tolerance = call.data["brightness_tolerance"]
        color_temp_tolerance = call.data["color_temp_tolerance"]
        rgb_color_tolerance = call.data["rgb_color_tolerance"]
        scope = write_tracker.resolve_scope_device(call.data["tracking_device_id"])
        scope_title = write_tracker.title_for_scope(scope)
        results: dict[str, Any] = {}
        for entity_id in call.data["entities"]:
            state = hass.states.get(entity_id)
            observed_ctx = write_tracker.observed_context_id(scope, entity_id)
            observed = (
                {
                    "context_id": observed_ctx,
                    "secondary_context_id": write_tracker.observed_secondary_context_id(scope, entity_id),
                    "target": write_tracker.observed_target(scope, entity_id),
                }
                if observed_ctx is not None
                else None
            )
            latest_ctx = write_tracker.latest_context_id(scope, entity_id)
            latest = (
                {
                    "context_id": latest_ctx,
                    "secondary_context_id": write_tracker.latest_secondary_context_id(scope, entity_id),
                    "target": write_tracker.latest_target(scope, entity_id),
                }
                if latest_ctx is not None
                else None
            )
            status, matched_via = classify(
                state is not None and state.state == "on",
                observed,
                latest,
                state.context.id if state is not None else None,
                state.attributes.get("brightness") if state is not None else None,
                state.attributes.get("color_temp_kelvin") if state is not None else None,
                state.attributes.get("rgb_color") if state is not None else None,
                brightness_tolerance,
                color_temp_tolerance,
                rgb_color_tolerance,
                state.attributes.get("min_color_temp_kelvin") if state is not None else None,
                state.attributes.get("max_color_temp_kelvin") if state is not None else None,
            )
            results[entity_id] = {
                "blocked": is_blocked(status),
                "status": status,
                "matched_via": matched_via,
                "scope": scope_title,
            }
        return {"results": results}

    async def claims_record(call: ServiceCall) -> ServiceResponse:
        """flare.claims_record

        Records that this call's own context just wrote `entities`,
        optionally with what each write actually asked for (`targets`) -
        a thin wrapper around write_tracker.async_record(), exposed
        standalone so a caller using claims_check on its own can
        participate in the same bookkeeping apply_lighting uses, without
        going through apply_lighting's brightness/curve logic. Call this
        *before* issuing whatever write you decided on, the same way
        apply_lighting does: a claim for a write that never lands is
        harmless (the light still matches its previous, confirmed claim),
        whereas a write with no claim - because the run was cancelled or
        failed between the two - reads as somebody else's change.

        Returns: {"recorded": [...]} - the entity_ids that were actually
        recorded, which is **not** necessarily everything passed in: the
        scope's tracking entity might not be up yet (see
        write_tracker.async_record's own docstring). Reporting the
        request back verbatim would tell a caller their write was
        tracked when nothing had happened.

        tracking_device_id (required): which FLARE tracking scope to record
        into - this service exists only to write tracking claims, so
        unlike apply_lighting there's nothing useful to do without one.
        """
        entities = call.data["entities"]
        targets = call.data.get("targets", {})
        scope = write_tracker.resolve_scope_device(call.data["tracking_device_id"])
        live_context_before_write = {
            e: (state.context.id if (state := hass.states.get(e)) is not None else None) for e in entities
        }
        await write_tracker.async_record(scope, entities, live_context_before_write, call.context.id, targets=targets)
        tracked = write_tracker.records_for_scope(scope)
        return {"recorded": [e for e in entities if e in tracked]}

    async def claims_clear(call: ServiceCall) -> ServiceResponse:
        """flare.claims_clear

        Discards `entities`' tracked observed/latest claims within
        tracking_device_id - the manual escape hatch for a light stuck
        "overridden" with no other way back (see write_tracking.py's
        async_clear docstring for why that can happen on its own for a
        light that never actually went unavailable). The next write to a
        cleared entity, from anyone, is treated exactly like a
        brand-new entity's first write - free to manage, no conflict
        check possible yet.

        Returns: {"cleared": [...]} - the entity_ids passed through.

        tracking_device_id (required): which FLARE tracking scope to clear
        entities out of - this service exists only to discard tracking
        claims, so unlike apply_lighting there's nothing useful to do
        without one.
        """
        entities = call.data["entities"]
        scope = write_tracker.resolve_scope_device(call.data["tracking_device_id"])
        await write_tracker.async_clear(scope, entities)
        return {"cleared": entities}

    async def compute_scene_coverage_service(call: ServiceCall) -> ServiceResponse:
        """flare.compute_scene_coverage

        Returns: {"scene_active", "scene_valid", "covered_entities",
        "uncovered_entities"} - see services.yaml for field docs.
        """
        result = compute_scene_coverage(
            scene_entity_id=call.data["scene_entity_id"],
            scope_entities=call.data["scope_entities"],
            target_entities=call.data["target_entities"],
            lookup=_build_scene_lookup(hass),
        )
        return {
            "scene_active": result.scene_active,
            "scene_valid": result.scene_valid,
            "covered_entities": result.covered_entities,
            "uncovered_entities": result.uncovered_entities,
        }

    # The services belong to the tracking entry: every one of them is
    # about which lights are being driven and by whom, and they need the
    # claim registry this entry owns.
    hass.services.async_register(
        DOMAIN,
        "compute_lighting_groups",
        compute_lighting_groups,
        schema=COMPUTE_LIGHTING_GROUPS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "compute_curve",
        compute_curve,
        schema=COMPUTE_CURVE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "compute_scene_coverage",
        compute_scene_coverage_service,
        schema=COMPUTE_SCENE_COVERAGE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "apply_lighting",
        apply_lighting,
        schema=APPLY_LIGHTING_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "turn_off",
        turn_off,
        schema=TURN_OFF_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "claims_check",
        claims_check,
        schema=CLAIMS_CHECK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "claims_record",
        claims_record,
        schema=CLAIMS_RECORD_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "claims_clear",
        claims_clear,
        schema=CLAIMS_CLEAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    for service in (
        "compute_lighting_groups",
        "compute_curve",
        "compute_scene_coverage",
        "apply_lighting",
        "turn_off",
        "claims_check",
        "claims_record",
        "claims_clear",
    ):
        hass.services.async_remove(DOMAIN, service)
