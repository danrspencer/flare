"""FLARE's nine services, registered by the Settings entry: adapters that
read HA state into the pure planners (grouping.py, scenes.py, curve.py,
override_protection.py) and dispatch the result. Field contracts are in
services.yaml."""

from __future__ import annotations

import asyncio

# Safe here, but not in the package __init__.py: importing the package's
# time.py platform rebinds `time` in the package namespace.
import time
from typing import Any

import voluptuous as vol
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_TRANSITION
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import Context, HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..const import (
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TWO_STEP_MODELS,
    DOMAIN,
)
from ..schedule.coordinator import CURVE_KEYS
from ..schedule.curve import phase_at, targets_for_phase
from .grouping import EntityLookup, Group, build_groups
from ..tracking.override_protection import is_blocked
from .scenes import SceneLookup, compute_scene_coverage
from .two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS, TWO_STEP_LABEL_ID, parse_patterns
from ..flares.identity import without_flares
from ..tracking.claims import ClaimRegistry

# FLARE drives and tracks lights only.
LIGHT_IDS = [cv.entity_domain(LIGHT_DOMAIN)]

# Who's writing, for override protection: a room, usually the calling
# automation (`this.entity_id`), and its lights, which it releases together.
# No room means "write, but track nothing".
ROOM_FIELDS = {
    vol.Optional("room_id"): vol.Any(None, cv.string),
    vol.Optional("room_entities"): vol.Any(None, [cv.entity_id]),
}

# Entity ID to a 0-255 level. null/false hand the light over, so they're
# kept as they are; vol.Any tries them first, before the number coerces.
BRIGHTNESS_LEVELS = vol.Schema(
    {cv.entity_id: vol.Any(None, False, vol.All(vol.Coerce(float), vol.Range(min=0)))}
)

# How close a light must be to match: unset or None takes the Settings
# entry's option.
TOLERANCE_FIELDS = {
    vol.Optional(CONF_MIN_BRIGHTNESS_CHANGE): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
    vol.Optional(CONF_MIN_COLOR_TEMP_CHANGE): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
}

COMPUTE_LIGHTING_GROUPS_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): LIGHT_IDS,
        vol.Optional("brightness_levels", default=dict): BRIGHTNESS_LEVELS,
        vol.Optional("brightness"): vol.Any(None, vol.Coerce(int)),
        vol.Required("color_temp_kelvin"): vol.Coerce(int),
        vol.Optional("two_step_label", default=TWO_STEP_LABEL_ID): cv.string,
        vol.Optional("prefer_rgb_color", default=False): cv.boolean,
        # Accepts an explicit None: a template reading a missing attribute
        # renders None, not an omitted key.
        vol.Optional("rgb_color"): vol.Any(None, vol.All([vol.Coerce(int)], vol.Length(min=3, max=3))),
        vol.Optional("force", default=False): cv.boolean,
        **TOLERANCE_FIELDS,
        **ROOM_FIELDS,
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

APPLY_LIGHTING_SCHEMA = COMPUTE_LIGHTING_GROUPS_SCHEMA.extend({vol.Required("transition"): vol.Coerce(float)})

TURN_OFF_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): LIGHT_IDS,
        vol.Optional("transition", default=0): vol.Coerce(float),
        **ROOM_FIELDS,
    }
)

CLAIMS_CHECK_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): LIGHT_IDS,
        **TOLERANCE_FIELDS,
    }
)

# Recording a claim, or an override, needs a room to release it with.
CLAIMS_RECORD_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): LIGHT_IDS,
        vol.Required("room_id"): cv.string,
        vol.Optional("room_entities"): [cv.entity_id],
        vol.Optional("targets", default=dict): dict,
    }
)

CLAIMS_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): LIGHT_IDS,
        vol.Required("room_id"): cv.string,
        vol.Optional("room_entities"): [cv.entity_id],
    }
)

CLAIMS_CLEAR_SCHEMA = vol.Schema({vol.Required("entities"): LIGHT_IDS})


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
        return list(s.attributes.get("entity_id") or []) if s else []

    return SceneLookup(exists=exists, covered_entities=covered_entities)


def _brightness(call: ServiceCall) -> int | None:
    """`brightness`, which is only optional if every light has a level."""
    brightness = call.data.get("brightness")
    if brightness is None:
        unlevelled = [e for e in call.data["entities"] if e not in call.data["brightness_levels"]]
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
        {ATTR_ENTITY_ID: entity_ids, ATTR_TRANSITION: half_transition, ATTR_BRIGHTNESS: target["brightness"]},
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
    """Registers the nine services for as long as the Settings entry is
    loaded."""

    def plan(call: ServiceCall) -> list[Group]:
        """build_groups for a compute_lighting_groups or apply_lighting call."""
        rgb_color = call.data.get("rgb_color")
        return build_groups(
            entities=without_flares(hass, call.data["entities"]),
            brightness_levels=call.data["brightness_levels"],
            sensor_brightness=_brightness(call),
            sensor_color_temp_kelvin=call.data["color_temp_kelvin"],
            lookup=_build_lookup(hass, registry, call.data.get("room_id")),
            two_step_label=call.data["two_step_label"],
            two_step_model_patterns=_two_step_model_patterns(entry),
            prefer_rgb_color=call.data["prefer_rgb_color"],
            rgb_color=tuple(rgb_color) if rgb_color else None,
            force=call.data["force"],
            **_tolerances(registry, call),
        )

    async def compute_lighting_groups(call: ServiceCall) -> ServiceResponse:
        """flare.compute_lighting_groups - see services.yaml."""
        return _groups_response(plan(call))

    async def compute_curve(call: ServiceCall) -> ServiceResponse:
        """flare.compute_curve - see services.yaml."""
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
        """flare.apply_lighting - see services.yaml.

        With force, the write still records a claim if a room is given, so the
        next non-forced call recognises it as ours."""
        room_id = call.data.get("room_id")
        room_entities = call.data.get("room_entities")
        groups = plan(call)
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

        # Lights already showing what this call would send get no write, so
        # an unclaimed one is claimed as it is.
        registry.adopt(room_id, [e for g in groups for e in g.already_set], room_entities)

        if tasks:
            await asyncio.gather(*tasks)

        return _groups_response(groups)

    async def turn_off(call: ServiceCall) -> None:
        """flare.turn_off - records {"state": "off"} claims, then switches off.

        One operation so callers can't get the order or the encoding wrong.
        No override protection: it turns off everything it's given."""
        entities = without_flares(hass, call.data["entities"])
        if not entities:
            return
        transition = call.data["transition"]
        registry.async_record(
            call.data.get("room_id"),
            entities,
            call.context.id,
            targets={e: {"state": "off"} for e in entities},
            room_entities=call.data.get("room_entities"),
        )
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
        for entity_id in call.data["entities"]:
            status, matched_via = registry.status(entity_id, **tolerances)
            results[entity_id] = {
                "blocked": is_blocked(status),
                "status": status,
                "matched_via": matched_via,
                "rooms": [registry.room_entity_id(key) for key in registry.rooms_of(entity_id)],
            }
        return {"results": results}

    async def claims_record(call: ServiceCall) -> ServiceResponse:
        """flare.claims_record - call it before your write. Returns the
        entities recorded."""
        entities = call.data["entities"]
        targets = call.data.get("targets", {})
        registry.async_record(
            call.data["room_id"],
            entities,
            call.context.id,
            targets=targets,
            room_entities=call.data.get("room_entities"),
        )
        tracked = registry.all_records()
        return {"recorded": [e for e in entities if e in tracked]}

    async def claims_override(call: ServiceCall) -> ServiceResponse:
        """flare.claims_override - marks lights as changed by someone else, so
        FLARE leaves them alone. The opposite of claims_clear."""
        entities = call.data["entities"]
        registry.async_override(call.data["room_id"], entities, call.data.get("room_entities"))
        return {"overridden": entities}

    async def claims_clear(call: ServiceCall) -> ServiceResponse:
        """flare.claims_clear - discards claims, the escape hatch for a light
        stuck "overridden"."""
        return {"cleared": registry.async_clear(call.data["entities"])}

    async def compute_scene_coverage_service(call: ServiceCall) -> ServiceResponse:
        """flare.compute_scene_coverage - see services.yaml."""
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

    services = {
        "compute_lighting_groups": (compute_lighting_groups, COMPUTE_LIGHTING_GROUPS_SCHEMA, SupportsResponse.ONLY),
        "compute_curve": (compute_curve, COMPUTE_CURVE_SCHEMA, SupportsResponse.ONLY),
        "compute_scene_coverage": (
            compute_scene_coverage_service,
            COMPUTE_SCENE_COVERAGE_SCHEMA,
            SupportsResponse.ONLY,
        ),
        "apply_lighting": (apply_lighting, APPLY_LIGHTING_SCHEMA, SupportsResponse.OPTIONAL),
        "turn_off": (turn_off, TURN_OFF_SCHEMA, SupportsResponse.NONE),
        "claims_check": (claims_check, CLAIMS_CHECK_SCHEMA, SupportsResponse.ONLY),
        "claims_record": (claims_record, CLAIMS_RECORD_SCHEMA, SupportsResponse.OPTIONAL),
        "claims_clear": (claims_clear, CLAIMS_CLEAR_SCHEMA, SupportsResponse.OPTIONAL),
        "claims_override": (claims_override, CLAIMS_OVERRIDE_SCHEMA, SupportsResponse.OPTIONAL),
    }
    for name, (handler, schema, response) in services.items():
        hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=response)

    @callback
    def _unregister() -> None:
        for name in services:
            hass.services.async_remove(DOMAIN, name)

    entry.async_on_unload(_unregister)
