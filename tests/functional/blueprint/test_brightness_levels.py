"""Per-light brightness levels, exclusions and idle brightness."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import (
    effective,
    light,
    occupancy,
    add_zone,
    setup_room_automation,
)


class TestBrightnessScaling:
    """docs/reference/blueprint.md#turning-lights-off-during-a-phase"""

    async def test_a_schedule_at_zero_brightness_still_reaches_one_not_off(
        self, hass, apply_lighting_calls
    ):
        """A curve brightness of 0 means "as dim as it goes". Unfloored, it would
        become multiplier 0, the off sentinel, and the room would go dark."""
        light(hass, "light.a", "on")
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 0, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls
        assert effective(apply_lighting_calls[-1], "light.a") == 1

    async def test_phase_exclude_list_sets_a_zero_multiplier_for_that_light(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on")
        light(hass, "light.excluded", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "light.excluded"]}, day_exclude_lights=["light.excluded"]
        )

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert effective(calls[-1], "light.excluded") == 0
        assert effective(calls[-1], "light.a") == 210, "the rest still follows the curve"

    async def test_brightness_template_wins_over_the_phase_exclude_list_on_collision(
        self, hass, apply_lighting_calls
    ):
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b"]},
            day_exclude_lights=["light.a", "light.b"],
            brightness_template="{{ {'light.a': 128} }}",
        )

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert effective(calls[-1], "light.a") == 128, "the template should win"
        assert effective(calls[-1], "light.b") == 0, "the exclude list fills in the rest"

    async def test_a_bare_number_from_the_brightness_template_applies_to_every_light(
        self, hass, apply_lighting_calls
    ):
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b"]},
            brightness_template="{{ 40 }}",
        )

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls
        call = apply_lighting_calls[-1]
        assert effective(call, "light.a") == 40
        assert effective(call, "light.b") == 40

    async def test_a_null_multiplier_light_is_not_turned_off_when_occupancy_clears(
        self, hass, turn_off_calls
    ):
        """null means "something else owns this" - e.g. a strip on its own
        automation - so an emptied room leaves it alone."""
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        light(hass, "light.handed_off", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.handed_off", "binary_sensor.occ"]},
            brightness_template="{{ {'light.handed_off': None} }}",
            no_motion_wait=0,
        )

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()

        assert turn_off_calls, "motion_off should still turn off the lights it does own"
        turned_off = turn_off_calls[-1].data["entities"]
        assert "light.a" in turned_off
        assert "light.handed_off" not in turned_off

    async def test_a_null_multiplier_light_is_released_from_override_protection(
        self, hass, apply_lighting_calls, claims_clear_calls
    ):
        """And its claim is released, rather than going stale into "overridden"."""
        kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
        add_zone(hass, kitchen.id, "kitchen")
        er.async_get(hass).async_get_or_create("light", "test", "light_a", suggested_object_id="a")
        er.async_get(hass).async_update_entity("light.a", area_id=kitchen.id)
        light(hass, "light.a", "on")
        light(hass, "light.handed_off", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.handed_off"]},
            brightness_template="{{ {'light.handed_off': None} }}",
        )
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert claims_clear_calls
        assert claims_clear_calls[-1].data["entities"] == ["light.handed_off"]

    async def test_a_zero_multiplier_light_is_still_turned_off_when_occupancy_clears(
        self, hass, turn_off_calls
    ):
        """0 is not null (`0 == false` in Jinja)."""
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        light(hass, "light.dimmed_out", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.dimmed_out", "binary_sensor.occ"]},
            brightness_template="{{ {'light.dimmed_out': 0} }}",
            no_motion_wait=0,
        )

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()

        assert turn_off_calls
        turned_off = turn_off_calls[-1].data["entities"]
        assert "light.a" in turned_off
        assert "light.dimmed_out" in turned_off

    async def test_reconcile_does_not_retry_turning_off_a_null_multiplier_light(
        self, hass, turn_off_calls
    ):
        """Self-heal doesn't retry turning it off either."""
        occupancy(hass, "binary_sensor.occ", "off")
        light(hass, "light.a", "off")
        light(hass, "light.handed_off", "on")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.handed_off", "binary_sensor.occ"]},
            brightness_template="{{ {'light.handed_off': None} }}",
        )

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
        await hass.async_block_till_done()

        assert turn_off_calls == []


class TestIdleBrightness:
    """docs/reference/blueprint.md#leaving-a-room-dimly-lit"""

    async def test_an_empty_room_dims_instead_of_going_off(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            no_motion_wait=0,
            day_idle_brightness=20,
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls, "the room went dark instead of dimming"
        assert effective(apply_lighting_calls[-1], "light.a") == 20
        for call in turn_off_calls:
            assert "light.a" not in call.data["entities"], "an idle light was switched off"

    async def test_lights_without_an_idle_level_still_go_off(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "binary_sensor.occ"]},
            no_motion_wait=0,
            idle_brightness_template="{{ {'light.a': 20} }}",
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.b"]
        assert effective(apply_lighting_calls[-1], "light.a") == 20

    async def test_a_dark_empty_room_is_lit_to_the_idle_level(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """The one way outside allow_turn_on to switch a light on."""
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            update_interval="/5",
            day_idle_brightness=20,
        )
        apply_lighting_calls.clear()

        frozen_time.tick(timedelta(minutes=6))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert apply_lighting_calls, "a dark empty room never reached its idle level"
        assert apply_lighting_calls[-1].data["entities"] == ["light.a"]
        assert effective(apply_lighting_calls[-1], "light.a") == 20

    async def test_a_room_with_no_occupancy_sensor_never_dims(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """occupancy.is_detected is false with no sensors, so such a room would
        otherwise sit at the idle level forever."""
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a"]},
            update_interval="/5",
            day_idle_brightness=20,
        )
        apply_lighting_calls.clear()

        frozen_time.tick(timedelta(minutes=6))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert apply_lighting_calls, "the tick should still have applied the curve"
        # Every call: the idle branch runs before the curve branch.
        assert not any(effective(c, "light.a") == 20 for c in apply_lighting_calls), (
            "dimmed a room that has no occupancy sensor"
        )

    async def test_it_waits_for_the_wait_time_before_dimming(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """PIR sensors flap, so dimming waits for the Wait time."""
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            update_interval="/5",
            no_motion_wait=3600,
            day_idle_brightness=20,
        )
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        apply_lighting_calls.clear()

        frozen_time.tick(timedelta(minutes=6))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert apply_lighting_calls, "the tick should still have run"
        assert not any(effective(c, "light.a") == 20 for c in apply_lighting_calls), (
            "dimmed before the Wait time had elapsed"
        )

    async def test_motion_applies_the_full_curve_not_the_idle_level(self, hass, apply_lighting_calls):
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            no_motion_wait=0,
            day_idle_brightness=20,
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        assert apply_lighting_calls
        assert effective(apply_lighting_calls[-1], "light.a") == 200

    async def test_motion_into_an_already_lit_idle_room_brightens_it(self, hass, apply_lighting_calls):
        """Motion into an already-lit idle room (nothing off) must still run, and
        at the motion transition: 1 is motion_on's, 5 is a tick's."""
        light(hass, "light.a", "on", brightness=20)
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            day_idle_brightness=20,
            motion_on_transition=1,
            background_transition=5,
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        assert apply_lighting_calls, "motion into an idle room did not reach apply_lighting"
        call = apply_lighting_calls[-1]
        assert effective(call, "light.a") == 200, "brightened to the idle level, not the curve"
        assert call.data["transition"] == 1, "used the background transition, so this came from a tick"

    async def test_a_template_level_alone_makes_that_lamp_the_only_nightlight(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        """With no phase value, a template level is the whole idle set: that lamp
        stays lit, the rest go dark, and the room reads as idle."""
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "binary_sensor.occ"]},
            no_motion_wait=0,
            idle_brightness_template="{{ {'light.a': 20} }}",
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls
        assert effective(apply_lighting_calls[-1], "light.a") == 20
        assert any("light.b" in c.data["entities"] for c in turn_off_calls), (
            "light.b has no idle level of its own, so it should go dark"
        )

    async def test_a_bare_number_from_the_idle_template_applies_to_every_light(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "binary_sensor.occ"]},
            no_motion_wait=0,
            idle_brightness_template="{{ 20 }}",
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls
        call = apply_lighting_calls[-1]
        assert effective(call, "light.a") == 20
        assert effective(call, "light.b") == 20

    async def test_leaving_a_phase_with_an_idle_level_turns_the_lights_off_not_up(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        """Leaving a phase with an idle level for one without: the lights are
        still on (so `occupied`), and must be turned off, not ramped to full."""
        occupancy(hass, "binary_sensor.occ", "off")
        light(hass, "light.a", "on", brightness=20)
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            no_motion_wait=0,
            day_idle_brightness=20,
        )
        apply_lighting_calls.clear()
        turn_off_calls.clear()

        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        assert any("light.a" in c.data["entities"] for c in turn_off_calls), (
            "the phase change left the light on rather than turning it off"
        )
        assert apply_lighting_calls == [], "the curve was applied, turning the nightlight up"

    async def test_the_per_phase_value_only_applies_in_its_phase(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        """Night configured, Day not: during Day, empty means dark."""
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            no_motion_wait=0,
            night_idle_brightness=20,
        )

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.a"]

    async def test_the_template_wins_over_the_phase_value_per_entity(
        self, hass, apply_lighting_calls, turn_off_calls
    ):
        """The phase value fills in every light; the template overrides by name."""
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "binary_sensor.occ"]},
            no_motion_wait=0,
            day_idle_brightness=20,
            idle_brightness_template="{{ {'light.b': 60} }}",
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        call = apply_lighting_calls[-1]
        assert effective(call, "light.a") == 20, "the phase value should fill in light.a"
        assert effective(call, "light.b") == 60, "the template should win for light.b"

    async def test_self_heal_does_not_retry_turning_off_an_idle_light(
        self, hass, turn_off_calls, frozen_time
    ):
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            update_interval="/5",
            day_idle_brightness=20,
        )
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        turn_off_calls.clear()

        frozen_time.tick(timedelta(minutes=6))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert turn_off_calls == []

    async def test_a_handed_off_light_is_not_given_an_idle_level(
        self, hass, apply_lighting_calls
    ):
        """null outranks an idle level."""
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            no_motion_wait=0,
            day_idle_brightness=20,
            brightness_template="{{ {'light.a': None} }}",
        )
        apply_lighting_calls.clear()

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        for call in apply_lighting_calls:
            assert "light.a" not in call.data["entities"]

    async def test_an_idle_light_does_not_ramp_itself_back_up(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """An idle light being on makes the room read as occupied; the next tick
        must not ramp it back up to the curve. Needs more than one tick to see."""
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            update_interval="/5",
            day_idle_brightness=20,
        )

        frozen_time.tick(timedelta(minutes=6))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        assert effective(apply_lighting_calls[-1], "light.a") == 20
        # The room now reads as occupied; the curve must still not apply.
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        apply_lighting_calls.clear()

        frozen_time.tick(timedelta(minutes=6))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert apply_lighting_calls, "the second tick should still have run"
        assert not any(effective(c, "light.a") == 200 for c in apply_lighting_calls), (
            "the idle light ramped itself back up to full brightness"
        )

    async def test_zero_means_the_room_still_goes_dark(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        """0 (the default) means no idle brightness."""
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            no_motion_wait=0,
            day_idle_brightness=0,
        )

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.a"]

    async def test_a_zero_in_the_template_is_not_an_idle_light(
        self, hass, turn_off_calls, apply_lighting_calls
    ):
        occupancy(hass, "binary_sensor.occ", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            no_motion_wait=0,
            day_idle_brightness=20,
            idle_brightness_template="{{ {'light.a': 0} }}",
        )

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()

        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.a"]
