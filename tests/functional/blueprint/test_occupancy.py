"""Occupancy turning rooms on and off, the allow_turn_on gate, and self-heal."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import (
    light,
    occupancy,
    add_zone,
    setup_room_automation,
)


class TestOccupancyDrivenOnOff:
    """docs/blueprint.md#when-lights-turn-on-and-off"""

    async def test_occupancy_detected_turns_on_off_lights_in_the_room(self, hass, apply_lighting_calls):
        occupancy(hass, "binary_sensor.occ", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"entity_id": ["light.a", "binary_sensor.occ"]})

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_the_turn_off_names_the_rooms_zone(self, hass, turn_off_calls):
        """Otherwise every emptied room's turn-off reads as an override."""
        zone = add_zone(hass)
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "binary_sensor.occ"]}, zone=zone, no_motion_wait=0
        )

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert turn_off_calls, "precondition: the room should have been turned off"
        assert turn_off_calls[-1].data["zone_device_id"] == zone

    async def test_occupancy_cleared_turns_lights_off_after_the_wait(self, hass, turn_off_calls):
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "binary_sensor.occ"]}, no_motion_wait=0
        )

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        # The `for:` is scheduled even at 0s.
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.a"]

    async def test_occupancy_cleared_does_not_turn_off_lights_while_a_second_sensor_is_still_on(
        self, hass, turn_off_calls
    ):
        """occupancy.cleared fires per sensor, even while another still reports
        occupied."""
        occupancy(hass, "binary_sensor.motion", "on")
        occupancy(hass, "binary_sensor.nightlight_override", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.motion", "binary_sensor.nightlight_override"]},
            no_motion_wait=0,
        )

        occupancy(hass, "binary_sensor.motion", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert turn_off_calls == []

    async def test_no_occupancy_sensor_still_updates_an_already_on_light(self, hass, apply_lighting_calls):
        """With no sensor, a light already on means in use."""
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_real_occupancy_sensor_reporting_unoccupied_still_updates_an_already_on_light(
        self, hass, apply_lighting_calls
    ):
        """Occupancy only turns lights on and off; it doesn't stop an on light
        following the curve."""
        occupancy(hass, "binary_sensor.occ", "off")
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"entity_id": ["light.a", "binary_sensor.occ"]})

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_fully_dark_unoccupied_room_periodic_tick_does_not_turn_anything_on(
        self, hass, apply_lighting_calls
    ):
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        # The tick did fire; apply_lighting isn't called because a dark, empty
        # room fails allow_turn_on.
        assert hass.states.get("automation.room").attributes.get("last_triggered") is not None
        assert apply_lighting_calls == []


class TestAllowTurnOn:
    """Only motion, a manual run, or the room already in use may switch a
    light on."""

    @pytest.mark.parametrize(
        "trigger_name",
        ["phase_change", "tick", "extra", "recovered"],
    )
    async def test_no_trigger_reaching_default_can_light_a_dark_empty_room(
        self, hass, apply_lighting_calls, scene_turn_on_calls, trigger_name
    ):
        """Swept across every trigger reaching default:, with a scene configured,
        so either turn-on path (or a new one) missing the gate is caught."""
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        hass.states.async_set("scene.night_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.a"]})
        hass.states.async_set("binary_sensor.extra_dep", "off", {})
        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            night_scene="scene.night_scene",
            extra_triggers=["binary_sensor.extra_dep"],
        )

        if trigger_name == "phase_change":
            hass.states.async_set("sensor.test_adaptive", "Night", {"brightness": 80, "color_temp": 2700})
        elif trigger_name == "tick":
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        elif trigger_name == "extra":
            hass.states.async_set("binary_sensor.extra_dep", "on", {})
        elif trigger_name == "recovered":
            # Comes back off, and must stay off.
            light(hass, "light.a", "unavailable")
            await hass.async_block_till_done()
            light(hass, "light.a", "off")
        await hass.async_block_till_done()

        assert hass.states.get("automation.room").attributes.get("last_triggered") is not None, (
            f"precondition: the {trigger_name} trigger must actually have run the automation"
        )
        assert scene_turn_on_calls == [], f"{trigger_name} lit an empty room via a scene"
        for call in apply_lighting_calls:
            assert call.data["entities"] == [], f"{trigger_name} lit an empty room via apply_lighting"

    async def test_manual_run_forces_the_tick_and_turns_on_off_lights(self, hass, apply_lighting_calls):
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        await hass.services.async_call("automation", "trigger", {"entity_id": "automation.room"}, blocking=True)
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]
        assert calls[-1].data["force"] is True

    async def test_occupied_room_lets_a_periodic_tick_turn_on_a_different_off_light(
        self, hass, apply_lighting_calls
    ):
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.on_light", "on", brightness=200, color_temp_kelvin=4000)
        light(hass, "light.off_light", "off")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": ["light.on_light", "light.off_light", "binary_sensor.occ"]}
        )

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and set(calls[-1].data["entities"]) == {"light.on_light", "light.off_light"}


class TestSelfHealing:
    """docs/blueprint.md#other-behaviour-worth-knowing"""

    async def test_reconcile_retries_turning_off_a_light_left_on_with_no_occupancy(
        self, hass, turn_off_calls, apply_lighting_calls, frozen_time
    ):
        """Wait time is checked with a template on last_changed, so the frozen
        clock has to actually move."""
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "binary_sensor.occ"]}, update_interval="/5"
        )
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        apply_lighting_calls.clear()

        frozen_time.tick(timedelta(minutes=6))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert turn_off_calls and "light.a" in turn_off_calls[-1].data["entities"]
        # Self-heal is exclusive of default:, which would re-light the lights it
        # just turned off from the stale entity list.
        assert apply_lighting_calls == []

    async def test_reconcile_does_nothing_while_occupied(self, hass, turn_off_calls, apply_lighting_calls):
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "binary_sensor.occ"]}, update_interval="/5"
        )
        apply_lighting_calls.clear()

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
        await hass.async_block_till_done()

        assert turn_off_calls == []
        # Occupied: falls through to default: as normal.
        assert apply_lighting_calls

    async def test_reconcile_ignores_a_momentary_occupancy_blip_shorter_than_wait_time(
        self, hass, turn_off_calls, frozen_time
    ):
        """A PIR sensor flaps off briefly while the room is occupied; a tick
        landing in a gap must still respect Wait time."""
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            update_interval="/5",
            no_motion_wait=120,
        )

        now = dt_util.utcnow()
        next_boundary = now.replace(second=0, microsecond=0) + timedelta(
            minutes=5 - (now.minute % 5), seconds=0
        )

        frozen_time.move_to(next_boundary - timedelta(seconds=30))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()

        # Clear for ~30s, against a 120s Wait time.
        frozen_time.move_to(next_boundary + timedelta(seconds=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert turn_off_calls == []
