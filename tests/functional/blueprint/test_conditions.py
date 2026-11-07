"""Conditions: the room runs only while every one is met."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import light, occupancy, setup_room_automation

ROOM = {"entity_id": ["light.a", "binary_sensor.occ"]}
ACTIVE = [{"condition": "state", "entity_id": "input_boolean.active", "state": "on"}]


def active(hass, state: str) -> None:
    hass.states.async_set("input_boolean.active", state)


def lit(calls):
    return [call for call in calls if call.data["entities"]]


async def tick(hass, frozen_time) -> None:
    frozen_time.tick(timedelta(minutes=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


class TestConditions:
    """docs/reference/blueprint.md#conditions"""

    async def _room(self, hass, *, lights: str, sensor: str, state: str, **inputs):
        occupancy(hass, "binary_sensor.occ", sensor)
        light(hass, "light.a", lights)
        active(hass, state)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target=ROOM, conditions=ACTIVE, no_motion_wait=0, **inputs)

    async def test_a_sensor_lights_the_room_while_the_conditions_are_met(self, hass, apply_lighting_calls):
        await self._room(hass, lights="off", sensor="off", state="on")

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_a_sensor_does_not_light_a_paused_room(self, hass, apply_lighting_calls):
        await self._room(hass, lights="off", sensor="off", state="off")

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []

    async def test_a_paused_room_does_not_turn_off(self, hass, turn_off_calls, frozen_time):
        await self._room(hass, lights="on", sensor="on", state="off")

        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        await tick(hass, frozen_time)

        assert turn_off_calls == []

    async def test_a_paused_room_does_not_follow_the_curve(self, hass, apply_lighting_calls, frozen_time):
        await self._room(hass, lights="on", sensor="on", state="off")

        await tick(hass, frozen_time)

        assert apply_lighting_calls == []

    async def test_an_empty_room_turns_off_once_the_conditions_are_met_again(
        self, hass, turn_off_calls, frozen_time
    ):
        await self._room(hass, lights="on", sensor="on", state="off")
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()

        active(hass, "on")
        await tick(hass, frozen_time)

        assert turn_off_calls[-1].data["entities"] == ["light.a"]

    async def test_a_manual_run_still_lights_a_paused_room(self, hass, apply_lighting_calls):
        await self._room(hass, lights="off", sensor="off", state="off")

        await hass.services.async_call("automation", "trigger", {"entity_id": "automation.room"}, blocking=True)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]
