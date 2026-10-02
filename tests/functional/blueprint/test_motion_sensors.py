"""Motion-class sensors work exactly like occupancy-class ones, alone or
alongside them."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import light, motion, occupancy, setup_room_automation


async def _wait_out(hass, frozen_time=None) -> None:
    """Let a `for: 0` cleared trigger fire."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()


class TestMotionSensors:
    """docs/reference/blueprint.md#room"""

    async def test_motion_detected_turns_on_off_lights_in_the_room(self, hass, apply_lighting_calls):
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.a", "binary_sensor.hall_motion"]})

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert apply_lighting_calls and apply_lighting_calls[-1].data["entities"] == ["light.a"]

    async def test_motion_cleared_turns_lights_off_after_the_wait(self, hass, turn_off_calls):
        motion(hass, "binary_sensor.hall_motion", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "binary_sensor.hall_motion"]}, no_motion_wait=0
        )

        motion(hass, "binary_sensor.hall_motion", "off")
        await hass.async_block_till_done()
        await _wait_out(hass)

        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.a"]

    async def test_motion_clearing_leaves_the_lights_on_while_an_occupancy_sensor_is_on(self, hass, turn_off_calls):
        motion(hass, "binary_sensor.hall_motion", "on")
        occupancy(hass, "binary_sensor.hall_presence", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.hall_motion", "binary_sensor.hall_presence"]},
            no_motion_wait=0,
        )

        motion(hass, "binary_sensor.hall_motion", "off")
        await hass.async_block_till_done()
        await _wait_out(hass)

        assert turn_off_calls == []

    async def test_occupancy_clearing_leaves_the_lights_on_while_a_motion_sensor_is_on(self, hass, turn_off_calls):
        motion(hass, "binary_sensor.hall_motion", "on")
        occupancy(hass, "binary_sensor.hall_presence", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.hall_motion", "binary_sensor.hall_presence"]},
            no_motion_wait=0,
        )

        occupancy(hass, "binary_sensor.hall_presence", "off")
        await hass.async_block_till_done()
        await _wait_out(hass)

        assert turn_off_calls == []

    async def test_a_motion_only_room_settles_to_its_idle_brightness(self, hass, apply_lighting_calls, frozen_time):
        """Idle brightness needs the room to have a sensor, and a motion sensor counts."""
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.hall_motion"]},
            no_motion_wait=0,
            night_idle_brightness=20,
            day_idle_brightness=20,
            evening_idle_brightness=20,
            morning_idle_brightness=20,
        )

        frozen_time.tick(timedelta(seconds=5))
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls and apply_lighting_calls[-1].data["entities"] == ["light.a"]
