"""FLARE's eight services, registered by the Settings entry: adapters that
read HA state into the pure planners (grouping.py, scenes.py, curve.py,
override_protection.py) and dispatch the result. Field contracts are in
services.yaml."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_TRANSITION, VALID_BRIGHTNESS, VALID_TRANSITION
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import Context, HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..const import (
    ATTR_ENTITIES,
    ATTR_ROOM_ENTITIES,
    ATTR_ROOM_ID,
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TWO_STEP_MODELS,
    DOMAIN,
    SERVICE_CLAIMS_OVERRIDE,
)
from ..schedule.coordinator import CURVE_KEYS
from ..schedule.curve import phase_at, targets_for_phase
from .grouping import EntityLookup, Group, build_groups
from ..tracking.override_protection import is_blocked
from .scenes import SceneLookup, compute_scene_coverage
from .two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS, parse_patterns
from ..flares.identity import without_flares
from ..tracking.claims import ClaimRegistry

# FLARE drives and tracks lights only.
LIGHT_IDS = [cv.entity_domain(LIGHT_DOMAIN)]

# Who's writing, for override protection: a room, usually the calling
# automation (`this.entity_id`). No room means "write, but track nothing".
ROOM_ID_FIELD = {vol.Optional(ATTR_ROOM_ID): vol.Any(None, cv.string)}

# Entity ID to a 0-255 level. null/false hand the light over, so they're
# kept as they are; vol.Any tries them first, before the number coerces.
BRIGHTNESS_LEVELS = vol.Schema(
    {cv.entity_id: vol.Any(None, False, cv.positive_float)}
)

# How close a light must be to match: unset or None takes the Settings
# entry's option.
TOLERANCE_FIELDS = {
    vol.Optional(CONF_MIN_BRIGHTNESS_CHANGE): vol.Any(None, cv.positive_float),
    vol.Optional(CONF_MIN_COLOR_TEMP_CHANGE): vol.Any(None, cv.positive_float),
}

APPLY_LIGHTING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITIES): LIGHT_IDS,
        vol.Optional("brightness_levels", default=dict): BRIGHTNESS_LEVELS,
        vol.Optional("brightness"): vol.Any(None, VALID_BRIGHTNESS),
        vol.Required("color_temp_kelvin"): cv.positive_int,
        vol.Optional("prefer_rgb_color", default=False): cv.boolean,
        # Accepts an explicit None: a template reading a missing attribute
        # renders None, not an omitted key. Otherwise as light.turn_on takes it.
        vol.Optional("rgb_color"): vol.Any(None, vol.All(vol.Coerce(tuple), vol.ExactSequence((cv.byte,) * 3))),
        vol.Optional("transition", default=0): VALID_TRANSITION,
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("dry_run", default=False): cv.boolean,
        **TOLERANCE_FIELDS,
        **ROOM_ID_FIELD,
        # The room's lights, which it releases together.
        vol.Optional(ATTR_ROOM_ENTITIES): vol.Any(None, cv.entity_ids),
    }
)

COMPUTE_CURVE_SCHEMA = vol.Schema(
    {
        vol.Required("morning"): vol.Coerce(float),
        vol.Required("day"): vol.Coerce(float),
        vol.Required("evening"): vol.Coerce(float),
        vol.Required("night"): vol.Coerce(float),
        vol.Optional("at"): vol.Coerce(float),
        # Left unset, the curve defaults apply.
        **{vol.Optional(key): vol.Coerce(int) for key in CURVE_KEYS},
    }
)

COMPUTE_SCENE_COVERAGE_SCHEMA = vol.Schema(
    {
        vol.Required("scene_entity_id"): cv.entity_id,
        vol.Required("scope_entities"): [cv.entity_id],
        vol.Required("target_entities"): [cv.entity_id],
    }
)

TURN_OFF_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITIES): LIGHT_IDS,
        vol.Optional("transition", default=0): VALID_TRANSITION,
    }
)

CLAIMS_CHECK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITIES): LIGHT_IDS,
        **TOLERANCE_FIELDS,
    }
)

# Recording a claim, or an override, needs a room to release it with.
CLAIMS_RECORD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITIES): LIGHT_IDS,
        vol.Required(ATTR_ROOM_ID): cv.string,
        vol.Optional(ATTR_ROOM_ENTITIES): cv.entity_ids,
        vol.Optional("targets", default=dict): dict,
    }
)

CLAIMS_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITIES): LIGHT_IDS,
        vol.Required(ATTR_ROOM_ID): cv.string,
        vol.Optional(ATTR_ROOM_ENTITIES): cv.entity_ids,
    }
)

CLAIMS_CLEAR_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITIES): LIGHT_IDS})


def _build_lookup(hass: HomeAssistant, tracker: ClaimRegistry, room_id: str | None) -> EntityLookup:
    """Adapts HA state/registries to grouping.py's EntityLookup. Without a
    room, no claims are read, so nothing is held back."""

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
        # Either an entity_id or a device_id.
        if not id_:
            return []
        entity_entry = er.async_get(hass).async_get(id_)
        if entity_entry is not None:
            return list(entity_entry.labels)
        device_entry = dr.async_get(hass).async_get(id_)
        if device_entry is not None:
            return list(device_entry.labels)
        return []

    return EntityLookup(
        state=hass.states.get,
        device_id=device_id,
        labels=labels,
        manufacturer_model=manufacturer_model,
        claims=lambda eid: tracker.record(eid) if room_id else None,
        tracking=bool(room_id),
    )


def _two_step_model_patterns(entry: ConfigEntry) -> list[str]:
    """The saved pattern list, or the shipped defaults if unset/empty."""
    configured = parse_patterns(entry.options.get(CONF_TWO_STEP_MODELS))
    return configured or list(DEFAULT_TWO_STEP_MODEL_PATTERNS)


def _tolerances(registry: ClaimRegistry, call: ServiceCall) -> dict[str, float]:
    """The call's own tolerances, else the integration's settings."""
    return {
        key: registry.tolerances[key] if call.data.get(key) is None else call.data[key]
        for key in (CONF_MIN_BRIGHTNESS_CHANGE, CONF_MIN_COLOR_TEMP_CHANGE)
    }


def _build_scene_lookup(hass: HomeAssistant) -> SceneLookup:
    def exists(scene_entity_id: str) -> bool:
        return hass.states.get(scene_entity_id) is not None

    def covered_entities(scene_entity_id: str) -> list:
        s = hass.states.get(scene_entity_id)
        return list(s.attributes.get(ATTR_ENTITY_ID) or []) if s else []

    return SceneLookup(exists=exists, covered_entities=covered_entities)


def _brightness(call: ServiceCall) -> int | None:
    """`brightness`, which is only optional if every light has a level."""
    brightness = call.data.get("brightness")
    if brightness is None:
        unlevelled = [e for e in call.data[ATTR_ENTITIES] if e not in call.data["brightness_levels"]]
        if unlevelled:
            raise ServiceValidationError(
                f"brightness is required for lights not in brightness_levels: {', '.join(unlevelled)}"
            )
    return brightness


def _groups_response(groups: list[Group]) -> ServiceResponse:
    return {
        "groups": [
            {
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
    target: dict,
    half_transition: float,
    *,
    brightness_context: Context,
    color_context: Context,
) -> None:
    """Brightness, wait, then brightness + colour, for bulbs that can't do
    both in one transition. Each step has its own context, so a device
    reporting just the first step is still recognised as ours. The caller
    creates the contexts, since the claims are recorded before dispatch."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_ids, ATTR_TRANSITION: half_transition, ATTR_BRIGHTNESS: target[ATTR_BRIGHTNESS]},
        blocking=True,
        context=brightness_context,
    )
    await asyncio.sleep(half_transition)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_ids, ATTR_TRANSITION: half_transition, **target},
        blocking=True,
        context=color_context,
    )


def async_setup_services(hass: HomeAssistant, entry: ConfigEntry, registry: ClaimRegistry) -> None:
    """Registers the eight services for as long as the Settings entry is
    loaded."""

    def plan(call: ServiceCall) -> list[Group]:
        """build_groups for an apply_lighting call."""
        rgb_color = call.data.get("rgb_color")
        return build_groups(
            entities=without_flares(hass, call.data[ATTR_ENTITIES]),
            brightness_levels=call.data["brightness_levels"],
            sensor_brightness=_brightness(call),
            sensor_color_temp_kelvin=call.data["color_temp_kelvin"],
            lookup=_build_lookup(hass, registry, call.data.get(ATTR_ROOM_ID)),
            two_step_model_patterns=_two_step_model_patterns(entry),
            prefer_rgb_color=call.data["prefer_rgb_color"],
            rgb_color=tuple(rgb_color) if rgb_color else None,
            force=call.data["force"],
            **_tolerances(registry, call),
        )

    async def compute_curve(call: ServiceCall) -> ServiceResponse:
        """flare.compute_curve - see services.yaml."""
        at = call.data.get("at", dt_util.utcnow().timestamp())
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
            "color_temp_kelvin": targets["kelvin"],
            "rgb_color": list(targets["rgb_color"]),
        }

    async def apply_lighting(call: ServiceCall) -> ServiceResponse:
        """flare.apply_lighting - see services.yaml.

        With force, the write still records a claim if a room is given, so the
        next non-forced call recognises it as ours."""
        room_id = call.data.get(ATTR_ROOM_ID)
        room_entities = call.data.get(ATTR_ROOM_ENTITIES)
        groups = plan(call)
        if call.data["dry_run"]:
            return _groups_response(groups)
        transition = call.data["transition"]
        half_transition = round(transition / 2, 1)

        # Our writes carry call.context, which is what the claims record.
        written_entities: list = []
        # What each write asked for - its group's target - to recognise it
        # echoed back under another context.
        write_targets: dict = {}
        # Two-step entities get their own pair of contexts, created now because
        # claims are recorded before dispatch: the colour step's as the primary,
        # the brightness step's as the secondary.
        context_id_overrides: dict = {}
        secondary_context_ids: dict = {}
        tasks = []
        for g in groups:
            # Each list, what it's sent, and whether in two steps.
            sends = [
                (g.needing_off, g.target, False),
                (g.combined, g.target, False),
                (g.combined_rgb, g.target_rgb, False),
                (g.two_step, g.target, True),
                (g.two_step_rgb, g.target_rgb, True),
            ]
            for lights, target, two_step in sends:
                if not lights:
                    continue
                written_entities.extend(lights)
                write_targets.update(dict.fromkeys(lights, target))
                if not two_step:
                    # An off-group's target is {"state": "off"}.
                    service, data = (SERVICE_TURN_OFF, {}) if "state" in target else (SERVICE_TURN_ON, target)
                    tasks.append(
                        hass.services.async_call(
                            LIGHT_DOMAIN,
                            service,
                            {ATTR_ENTITY_ID: lights, ATTR_TRANSITION: transition, **data},
                            blocking=True,
                            context=call.context,
                        )
                    )
                    continue
                brightness_context = Context(parent_id=call.context.id)
                color_context = Context(parent_id=call.context.id)
                context_id_overrides.update(dict.fromkeys(lights, color_context.id))
                secondary_context_ids.update(dict.fromkeys(lights, brightness_context.id))
                tasks.append(
                    _two_step_turn_on(
                        hass,
                        lights,
                        target,
                        half_transition,
                        brightness_context=brightness_context,
                        color_context=color_context,
                    )
                )

        # Recorded BEFORE dispatch, so a run that fails or is cancelled part-way
        # (e.g. by `mode: restart` between two-step steps) still leaves claims for
        # lights that changed. A claim for a write that never lands is harmless:
        # the light still matches its previous claim. No awaits in between, so
        # planning and recording are one step.
        if written_entities:
            registry.async_record(
                room_id,
                written_entities,
                call.context.id,
                targets=write_targets,
                secondary_context_ids=secondary_context_ids,
                context_id_overrides=context_id_overrides,
                room_entities=room_entities,
            )

        if tasks:
            await asyncio.gather(*tasks)

        return _groups_response(groups)

    async def turn_off(call: ServiceCall) -> None:
        """flare.turn_off - records {"state": "off"} on the lights FLARE
        claims, then switches off, so a light switched off in a room that
        stays lit is still FLARE's.

        One operation so callers can't get the order or the encoding wrong.
        No override protection: it turns off everything it's given."""
        entities = without_flares(hass, call.data[ATTR_ENTITIES])
        if not entities:
            return
        transition = call.data["transition"]
        registry.async_record_off(entities, call.context.id)
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entities, ATTR_TRANSITION: transition},
            blocking=True,
            context=call.context,
        )

    async def claims_check(call: ServiceCall) -> ServiceResponse:
        """flare.claims_check - override protection as a standalone question.
        See services.yaml. No `force`, since forcing makes every answer "not
        blocked"."""
        tolerances = _tolerances(registry, call)
        results: dict[str, Any] = {}
        for entity_id in call.data[ATTR_ENTITIES]:
            status, matched_via = registry.status(entity_id, **tolerances)
            results[entity_id] = {
                "blocked": is_blocked(status),
                "status": status,
                "matched_via": matched_via,
                "rooms": [registry.room_entity_id(key) for key in registry.rooms_of(entity_id)],
            }
        return {"results": results}

    async def claims_record(call: ServiceCall) -> None:
        """flare.claims_record - call it before your write."""
        entities = call.data[ATTR_ENTITIES]
        targets = call.data.get("targets", {})
        registry.async_record(
            call.data[ATTR_ROOM_ID],
            entities,
            call.context.id,
            targets=targets,
            room_entities=call.data.get(ATTR_ROOM_ENTITIES),
        )

    async def claims_override(call: ServiceCall) -> None:
        """flare.claims_override - marks lights as changed by someone else, so
        FLARE leaves them alone. The opposite of claims_clear."""
        registry.async_override(call.data[ATTR_ROOM_ID], call.data[ATTR_ENTITIES], call.data.get(ATTR_ROOM_ENTITIES))

    async def claims_clear(call: ServiceCall) -> ServiceResponse:
        """flare.claims_clear - discards claims, the escape hatch for a light
        stuck "overridden"."""
        return {"cleared": registry.async_clear(call.data[ATTR_ENTITIES])}

    async def compute_scene_coverage_service(call: ServiceCall) -> ServiceResponse:
        """flare.compute_scene_coverage - see services.yaml."""
        result = compute_scene_coverage(
            scene_entity_id=call.data["scene_entity_id"],
            scope_entities=call.data["scope_entities"],
            target_entities=call.data["target_entities"],
            lookup=_build_scene_lookup(hass),
        )
        return {
            "scene_valid": result.scene_valid,
            "covered_entities": result.covered_entities,
            "uncovered_entities": result.uncovered_entities,
        }

    services = {
        "compute_curve": (compute_curve, COMPUTE_CURVE_SCHEMA, SupportsResponse.ONLY),
        "compute_scene_coverage": (
            compute_scene_coverage_service,
            COMPUTE_SCENE_COVERAGE_SCHEMA,
            SupportsResponse.ONLY,
        ),
        "apply_lighting": (apply_lighting, APPLY_LIGHTING_SCHEMA, SupportsResponse.OPTIONAL),
        "turn_off": (turn_off, TURN_OFF_SCHEMA, SupportsResponse.NONE),
        "claims_check": (claims_check, CLAIMS_CHECK_SCHEMA, SupportsResponse.ONLY),
        "claims_record": (claims_record, CLAIMS_RECORD_SCHEMA, SupportsResponse.NONE),
        "claims_clear": (claims_clear, CLAIMS_CLEAR_SCHEMA, SupportsResponse.OPTIONAL),
        SERVICE_CLAIMS_OVERRIDE: (claims_override, CLAIMS_OVERRIDE_SCHEMA, SupportsResponse.NONE),
    }
    for name, (handler, schema, response) in services.items():
        hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=response)

    @callback
    def _unregister() -> None:
        for name in services:
            hass.services.async_remove(DOMAIN, name)

    entry.async_on_unload(_unregister)
