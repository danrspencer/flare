"""FLARE's nine services, registered by the Zones entry: adapters that
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
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..const import (
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TWO_STEP_MODELS,
    DEFAULT_MIN_BRIGHTNESS_CHANGE,
    DEFAULT_MIN_COLOR_TEMP_CHANGE,
    DOMAIN,
)
from ..schedule.coordinator import CURVE_KEYS
from ..schedule.curve import phase_at, targets_for_phase
from .grouping import EntityLookup, Group, build_groups, target_brightness
from ..zone.matching import DEFAULT_BRIGHTNESS_TOLERANCE, DEFAULT_COLOR_TEMP_TOLERANCE, DEFAULT_RGB_COLOR_TOLERANCE
from ..zone.override_protection import classify_state, is_blocked
from .scenes import SceneLookup, compute_scene_coverage
from .two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS, TWO_STEP_LABEL_ID, parse_patterns
from ..zone.claims import ClaimRegistry

# Entity ID to a 0-255 level. null/false hand the light over, so they're
# kept as they are; vol.Any tries them first, before the number coerces.
BRIGHTNESS_LEVELS = vol.Schema(
    {cv.entity_id: vol.Any(None, False, vol.All(vol.Coerce(float), vol.Range(min=0)))}
)

COMPUTE_LIGHTING_GROUPS_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Optional("brightness_levels", default=dict): BRIGHTNESS_LEVELS,
        vol.Optional("brightness"): vol.Any(None, vol.Coerce(int)),
        vol.Required("color_temp_kelvin"): vol.Coerce(int),
        vol.Optional("brightness_tolerance", default=DEFAULT_BRIGHTNESS_TOLERANCE): vol.Coerce(int),
        vol.Optional("color_temp_tolerance", default=DEFAULT_COLOR_TEMP_TOLERANCE): vol.Coerce(int),
        vol.Optional("two_step_label", default=TWO_STEP_LABEL_ID): cv.string,
        vol.Optional("prefer_rgb_color", default=False): cv.boolean,
        # Accepts an explicit None: a template reading a missing attribute
        # renders None, not an omitted key.
        vol.Optional("rgb_color"): vol.Any(None, vol.All([vol.Coerce(int)], vol.Length(min=3, max=3))),
        vol.Optional("rgb_color_tolerance", default=DEFAULT_RGB_COLOR_TOLERANCE): vol.Coerce(int),
        vol.Optional("force", default=False): cv.boolean,
        # None means "use the integration's setting".
        vol.Optional(CONF_MIN_BRIGHTNESS_CHANGE): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(CONF_MIN_COLOR_TEMP_CHANGE): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
        # None means "write, but track nothing".
        vol.Optional("zone_device_id"): vol.Any(None, cv.string),
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

APPLY_LIGHTING_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Optional("brightness_levels", default=dict): BRIGHTNESS_LEVELS,
        vol.Optional("brightness"): vol.Any(None, vol.Coerce(int)),
        vol.Required("color_temp_kelvin"): vol.Coerce(int),
        vol.Required("transition"): vol.Coerce(float),
        vol.Optional("brightness_tolerance", default=DEFAULT_BRIGHTNESS_TOLERANCE): vol.Coerce(int),
        vol.Optional("color_temp_tolerance", default=DEFAULT_COLOR_TEMP_TOLERANCE): vol.Coerce(int),
        vol.Optional("two_step_label", default=TWO_STEP_LABEL_ID): cv.string,
        vol.Optional("prefer_rgb_color", default=False): cv.boolean,
        # Accepts an explicit None, as above.
        vol.Optional("rgb_color"): vol.Any(None, vol.All([vol.Coerce(int)], vol.Length(min=3, max=3))),
        vol.Optional("rgb_color_tolerance", default=DEFAULT_RGB_COLOR_TOLERANCE): vol.Coerce(int),
        vol.Optional("force", default=False): cv.boolean,
        # None means "use the integration's setting".
        vol.Optional(CONF_MIN_BRIGHTNESS_CHANGE): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
        vol.Optional(CONF_MIN_COLOR_TEMP_CHANGE): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
        # None means "write, but track nothing".
        vol.Optional("zone_device_id"): vol.Any(None, cv.string),
    }
)

TURN_OFF_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Optional("transition", default=0): vol.Coerce(float),
        # None turns the lights off untracked.
        vol.Optional("zone_device_id"): vol.Any(None, cv.string),
    }
)

# The claims_* services exist only to read or write claims, so a zone is
# required.
CLAIMS_CHECK_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Required("zone_device_id"): cv.string,
        vol.Optional("brightness_tolerance", default=DEFAULT_BRIGHTNESS_TOLERANCE): vol.Coerce(int),
        vol.Optional("color_temp_tolerance", default=DEFAULT_COLOR_TEMP_TOLERANCE): vol.Coerce(int),
        vol.Optional("rgb_color_tolerance", default=DEFAULT_RGB_COLOR_TOLERANCE): vol.Coerce(int),
    }
)

CLAIMS_RECORD_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Required("zone_device_id"): cv.string,
        vol.Optional("targets", default=dict): dict,
    }
)

CLAIMS_CLEAR_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): [cv.entity_id],
        vol.Required("zone_device_id"): cv.string,
    }
)


def _build_lookup(hass: HomeAssistant, tracker: ClaimRegistry, subentry_id: str | None) -> EntityLookup:
    """Adapts HA state/registries to grouping.py's EntityLookup, with the
    caller's zone bound into the claims lookup."""

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
        claims=lambda eid: tracker.record(subentry_id, eid),
        reconnected_at=tracker.reconnected_at,
    )


def _two_step_model_patterns(entry: ConfigEntry) -> list[str]:
    """The saved pattern list, or the shipped defaults if unset/empty."""
    configured = parse_patterns(entry.options.get(CONF_TWO_STEP_MODELS))
    return configured or list(DEFAULT_TWO_STEP_MODEL_PATTERNS)


def _min_change(entry: ConfigEntry, call: ServiceCall, key: str, default: float) -> float:
    """The call's own value, else the integration's setting."""
    value = call.data.get(key)
    if value is None:
        value = entry.options.get(key, default)
    return float(value)


def _min_changes(entry: ConfigEntry, call: ServiceCall) -> dict[str, float]:
    return {
        "min_brightness_change": _min_change(entry, call, CONF_MIN_BRIGHTNESS_CHANGE, DEFAULT_MIN_BRIGHTNESS_CHANGE),
        "min_color_temp_change": _min_change(entry, call, CONF_MIN_COLOR_TEMP_CHANGE, DEFAULT_MIN_COLOR_TEMP_CHANGE),
    }


def _build_scene_lookup(hass: HomeAssistant) -> SceneLookup:
    def exists(scene_entity_id: str) -> bool:
        return hass.states.get(scene_entity_id) is not None

    def covered_entities(scene_entity_id: str) -> list:
        s = hass.states.get(scene_entity_id)
        return list(s.attributes.get("entity_id", [])) if s else []

    return SceneLookup(exists=exists, covered_entities=covered_entities)


def _without_flares(hass: HomeAssistant, entities: list[str]) -> list[str]:
    """Drops flares' own lights: a flare in its room's area would otherwise
    be sent the room's values, and pass them on to every light as an override."""
    registry = er.async_get(hass)
    return [
        e for e in entities
        if not ((entry := registry.async_get(e)) and entry.platform == DOMAIN and entry.domain == "light")
    ]


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
    brightness: int,
    half_transition: float,
    *,
    brightness_context: Context,
    color_context: Context,
    color_temp_kelvin: int | None = None,
    rgb_color: list | None = None,
) -> None:
    """Brightness, wait, then brightness + colour, for bulbs that can't do
    both in one transition. Each step has its own context, so a device
    reporting just the first step is still recognised as ours. The caller
    creates the contexts, since the claims are recorded before dispatch."""
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


def async_setup_services(hass: HomeAssistant, entry: ConfigEntry, registry: ClaimRegistry) -> None:
    """Registers the nine services against this Zones entry."""

    async def compute_lighting_groups(call: ServiceCall) -> ServiceResponse:
        """flare.compute_lighting_groups - see services.yaml."""
        rgb_color = call.data.get("rgb_color")
        zone = registry.resolve_zone_device(call.data.get("zone_device_id"))
        groups = build_groups(
            entities=_without_flares(hass, call.data["entities"]),
            brightness_levels=call.data["brightness_levels"],
            sensor_brightness=_brightness(call),
            sensor_color_temp_kelvin=call.data["color_temp_kelvin"],
            lookup=_build_lookup(hass, registry, zone),
            brightness_tolerance=call.data["brightness_tolerance"],
            color_temp_tolerance=call.data["color_temp_tolerance"],
            two_step_label=call.data["two_step_label"],
            two_step_model_patterns=_two_step_model_patterns(entry),
            prefer_rgb_color=call.data["prefer_rgb_color"],
            rgb_color=tuple(rgb_color) if rgb_color else None,
            rgb_color_tolerance=call.data["rgb_color_tolerance"],
            force=call.data["force"],
            **_min_changes(entry, call),
        )
        return _groups_response(groups)

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

        With force, the write still records a claim if a zone is given, so the
        next non-forced call recognises it as ours."""
        force = call.data["force"]
        brightness = _brightness(call)
        rgb_color_raw = call.data.get("rgb_color")
        rgb_color = tuple(rgb_color_raw) if rgb_color_raw else None
        zone = registry.resolve_zone_device(call.data.get("zone_device_id"))
        lookup = _build_lookup(hass, registry, zone)
        groups = build_groups(
            entities=_without_flares(hass, call.data["entities"]),
            brightness_levels=call.data["brightness_levels"],
            sensor_brightness=brightness,
            sensor_color_temp_kelvin=call.data["color_temp_kelvin"],
            lookup=lookup,
            brightness_tolerance=call.data["brightness_tolerance"],
            color_temp_tolerance=call.data["color_temp_tolerance"],
            two_step_label=call.data["two_step_label"],
            two_step_model_patterns=_two_step_model_patterns(entry),
            prefer_rgb_color=call.data["prefer_rgb_color"],
            rgb_color=rgb_color,
            rgb_color_tolerance=call.data["rgb_color_tolerance"],
            force=force,
            **_min_changes(entry, call),
        )

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
            if g.needing_off:
                written_entities.extend(g.needing_off)
                for e in g.needing_off:
                    write_targets[e] = g.target
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
                    write_targets[e] = g.target
                tasks.append(
                    hass.services.async_call(
                        "light",
                        "turn_on",
                        {"entity_id": g.combined, "transition": transition, **g.target},
                        blocking=True,
                        context=call.context,
                    )
                )
            if g.combined_rgb:
                written_entities.extend(g.combined_rgb)
                for e in g.combined_rgb:
                    write_targets[e] = g.target_rgb
                tasks.append(
                    hass.services.async_call(
                        "light",
                        "turn_on",
                        {"entity_id": g.combined_rgb, "transition": transition, **g.target_rgb},
                        blocking=True,
                        context=call.context,
                    )
                )
            if g.two_step:
                written_entities.extend(g.two_step)
                brightness_context = Context(parent_id=call.context.id)
                color_context = Context(parent_id=call.context.id)
                for e in g.two_step:
                    write_targets[e] = g.target
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
                        color_temp_kelvin=g.target["color_temp_kelvin"],
                    )
                )
            if g.two_step_rgb:
                written_entities.extend(g.two_step_rgb)
                brightness_context = Context(parent_id=call.context.id)
                color_context = Context(parent_id=call.context.id)
                for e in g.two_step_rgb:
                    write_targets[e] = g.target_rgb
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
                        rgb_color=g.target_rgb["rgb_color"],
                    )
                )

        # Before dispatch, so it can't include this call's own writes.
        live_context_before_write = {
            e: (state.context.id if (state := hass.states.get(e)) is not None else None) for e in written_entities
        }

        # Recorded BEFORE dispatch, so a run that fails or is cancelled part-way
        # (e.g. by `mode: restart` between two-step steps) still leaves claims for
        # lights that changed. A claim for a write that never lands is harmless:
        # the light still matches its previous claim. No awaits in between, so
        # planning and recording are one step.
        if written_entities:
            await registry.async_record(
                zone,
                written_entities,
                live_context_before_write,
                call.context.id,
                targets=write_targets,
                secondary_context_ids=secondary_context_ids,
                context_id_overrides=context_id_overrides,
            )

        # Lights already showing what this call would send get no write, so
        # an unclaimed one is claimed as it is.
        registry.adopt(
            zone,
            [
                e
                for e in _without_flares(hass, call.data["entities"])
                if e not in written_entities
                and (target_brightness(e, call.data["brightness_levels"], brightness) or 0) > 0
                and lookup.claims(e) is None
            ],
        )

        if tasks:
            await asyncio.gather(*tasks)

        return _groups_response(groups)

    async def turn_off(call: ServiceCall) -> None:
        """flare.turn_off - records {"state": "off"} claims, then switches off.

        One operation so callers can't get the order or the encoding wrong.
        No override protection: it turns off everything it's given."""
        entities = _without_flares(hass, call.data["entities"])
        if not entities:
            return
        transition = call.data["transition"]
        zone = registry.resolve_zone_device(call.data.get("zone_device_id"))
        live_context_before_write = {
            e: (state.context.id if (state := hass.states.get(e)) is not None else None) for e in entities
        }
        await registry.async_record(
            zone,
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
        """flare.claims_check - override protection as a standalone question.
        See services.yaml. No `force`, since forcing makes every answer "not
        blocked"."""
        brightness_tolerance = call.data["brightness_tolerance"]
        color_temp_tolerance = call.data["color_temp_tolerance"]
        rgb_color_tolerance = call.data["rgb_color_tolerance"]
        zone = registry.resolve_zone_device(call.data["zone_device_id"])
        zone_title = registry.zone_title(zone)
        results: dict[str, Any] = {}
        for entity_id in call.data["entities"]:
            status, matched_via = classify_state(
                hass.states.get(entity_id),
                registry.record(zone, entity_id),
                brightness_tolerance,
                color_temp_tolerance,
                rgb_color_tolerance,
                registry.reconnected_at(entity_id),
            )
            results[entity_id] = {
                "blocked": is_blocked(status),
                "status": status,
                "matched_via": matched_via,
                "zone": zone_title,
            }
        return {"results": results}

    async def claims_record(call: ServiceCall) -> ServiceResponse:
        """flare.claims_record - call it before your write. Returns only the
        entities actually recorded, which may be fewer if the zone's claims
        entity isn't up yet."""
        entities = call.data["entities"]
        targets = call.data.get("targets", {})
        zone = registry.resolve_zone_device(call.data["zone_device_id"])
        live_context_before_write = {
            e: (state.context.id if (state := hass.states.get(e)) is not None else None) for e in entities
        }
        await registry.async_record(zone, entities, live_context_before_write, call.context.id, targets=targets)
        tracked = registry.records_for_zone(zone)
        return {"recorded": [e for e in entities if e in tracked]}

    async def claims_override(call: ServiceCall) -> ServiceResponse:
        """flare.claims_override - marks lights as changed by someone else, so
        FLARE leaves them alone. The opposite of claims_clear."""
        entities = call.data["entities"]
        zone = registry.resolve_zone_device(call.data["zone_device_id"])
        await registry.async_override(zone, entities)
        return {"overridden": entities}

    async def claims_clear(call: ServiceCall) -> ServiceResponse:
        """flare.claims_clear - discards claims, the escape hatch for a light
        stuck "overridden"."""
        entities = call.data["entities"]
        zone = registry.resolve_zone_device(call.data["zone_device_id"])
        await registry.async_clear(zone, entities)
        return {"cleared": entities}

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
    hass.services.async_register(
        DOMAIN,
        "claims_override",
        claims_override,
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
        "claims_override",
    ):
        hass.services.async_remove(DOMAIN, service)
