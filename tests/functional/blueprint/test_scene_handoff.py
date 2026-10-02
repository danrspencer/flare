"""Handing a room, or part of it, to a scene."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import (
    light,
    occupancy,
    add_zone,
    setup_room_automation,
)


class TestSceneHandoff:
    """docs/reference/blueprint.md#scenes"""

    async def test_valid_scene_activates_via_a_phase_change_and_flare_only_covers_uncovered_entities(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        """A phase change activates the new phase's scene even while one is
        already active, with no fresh motion needed."""
        light(hass, "light.covered", "on")
        light(hass, "light.uncovered", "on")
        hass.states.async_set("scene.evening_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.covered"]})
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.covered", "light.uncovered"]},
            evening_scene="scene.evening_scene",
        )

        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        assert scene_turn_on_calls and scene_turn_on_calls[-1].data["entity_id"] == ["scene.evening_scene"]
        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.uncovered"]

    async def test_scene_covered_lights_are_released_from_override_protection(
        self, hass, apply_lighting_calls, scene_turn_on_calls, claims_clear_calls
    ):
        """A scene-owned light isn't written, so its claim is released rather
        than going stale into "overridden"."""
        kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
        add_zone(hass, kitchen.id, "kitchen")
        er.async_get(hass).async_get_or_create("light", "test", "light_covered", suggested_object_id="covered")
        er.async_get(hass).async_update_entity("light.covered", area_id=kitchen.id)
        light(hass, "light.covered", "on")
        light(hass, "light.uncovered", "on")
        hass.states.async_set("scene.evening_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.covered"]})
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.covered", "light.uncovered"]},
            evening_scene="scene.evening_scene",
        )
        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        assert claims_clear_calls
        assert claims_clear_calls[-1].data["entities"] == ["light.covered"]
        # Still adaptively managed, so not released.
        assert apply_lighting_calls[-1].data["entities"] == ["light.uncovered"]

    async def test_a_scene_reaching_outside_scope_releases_nothing(
        self, hass, apply_lighting_calls, claims_clear_calls
    ):
        """A scene reaching outside the room counts as no scene, so nothing is
        released."""
        light(hass, "light.a", "on")
        light(hass, "light.outside_the_room", "on")
        hass.states.async_set(
            "scene.reaches_out", "2024-01-01T00:00:00+00:00",
            {"entity_id": ["light.a", "light.outside_the_room"]},
        )
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": "light.a"}, evening_scene="scene.reaches_out"
        )
        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        assert claims_clear_calls == []
        assert apply_lighting_calls[-1].data["entities"] == ["light.a"]

    async def test_scene_recheck_is_skipped_on_a_same_phase_attribute_only_tick(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        """A scene is re-activated only on a real phase change, or it would stomp
        manual changes every minute."""
        light(hass, "light.covered", "on")
        hass.states.async_set("scene.evening_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.covered"]})
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": "light.covered"}, evening_scene="scene.evening_scene"
        )

        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()
        assert len(scene_turn_on_calls) == 1

        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 140, "color_temp": 3000})
        await hass.async_block_till_done()

        assert len(scene_turn_on_calls) == 1

    async def test_scene_reaching_outside_scope_is_treated_as_invalid(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        light(hass, "light.a", "on")
        hass.states.async_set(
            "scene.bad_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.a", "light.not_in_room"]}
        )
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": "light.a"}, scene_template="scene.bad_scene"
        )

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert scene_turn_on_calls == []
        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_a_malformed_scene_template_does_not_crash_the_whole_automation(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        """A scene_template rendering "{}" would make states[...] raise in
        variables:, failing every trigger. It must count as no scene."""
        light(hass, "light.a", "on")
        await setup_room_automation(
            hass, room_target={"entity_id": "light.a"}, scene_template="{{ {} }}"
        )

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert scene_turn_on_calls == []
        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_phase_scene_is_used_when_the_template_returns_nothing(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        light(hass, "light.covered", "on")
        hass.states.async_set("scene.day_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.covered"]})
        hass.states.async_set("sensor.test_adaptive", "Night", {"brightness": 80, "color_temp": 2700})
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"entity_id": "light.covered"}, day_scene="scene.day_scene")

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        await hass.async_block_till_done()

        assert scene_turn_on_calls and scene_turn_on_calls[-1].data["entity_id"] == ["scene.day_scene"]

    async def test_a_phase_change_does_not_light_an_empty_room(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        """Scene activation is behind allow_turn_on too. A scene can't be filtered
        per light, so the gate must stop the step entirely."""
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        hass.states.async_set("scene.night_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.a"]})
        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            night_scene="scene.night_scene",
        )

        hass.states.async_set("sensor.test_adaptive", "Night", {"brightness": 80, "color_temp": 2700})
        await hass.async_block_till_done()

        assert hass.states.get("automation.room").attributes.get("last_triggered") is not None, (
            "precondition: the phase change must actually have run the automation"
        )
        assert scene_turn_on_calls == [], "a phase change must not light an empty room"
        for call in apply_lighting_calls:
            assert call.data["entities"] == []

    async def test_motion_into_a_dark_room_still_activates_the_scene(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        """Motion is allowed to light a room, so it must still activate the scene."""
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        hass.states.async_set("scene.night_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.a"]})
        hass.states.async_set("sensor.test_adaptive", "Night", {"brightness": 80, "color_temp": 2700})
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            night_scene="scene.night_scene",
        )

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        assert scene_turn_on_calls and scene_turn_on_calls[-1].data["entity_id"] == ["scene.night_scene"]
