"""Presence-class sensors work exactly like occupancy- and motion-class ones.

Home Assistant has no `presence.*` trigger platform - it ships `occupancy.*`
and `motion.*` only - so the blueprint watches presence sensors with a
template. These cover that template as well as the room_occupancy_entities
filter it shares with the other two classes.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import (
    light,
    motion,
    presence,
    setup_room_automation,
)


async def _wait_out(hass) -> None:
    """Let a `for: 0` cleared trigger fire."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()


class TestPresenceSensors:
    """docs/reference/blueprint.md#room"""

    async def test_presence_detected_turns_on_off_lights_in_the_room(self, hass, apply_lighting_calls):
        presence(hass, "binary_sensor.hall_presence", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.a", "binary_sensor.hall_presence"]})

        presence(hass, "binary_sensor.hall_presence", "on")
        await hass.async_block_till_done()

        assert apply_lighting_calls and apply_lighting_calls[-1].data["entities"] == ["light.a"]

    async def test_presence_cleared_turns_lights_off_after_the_wait(self, hass, turn_off_calls):
        presence(hass, "binary_sensor.hall_presence", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "binary_sensor.hall_presence"]}, no_motion_wait=0
        )

        presence(hass, "binary_sensor.hall_presence", "off")
        await hass.async_block_till_done()
        await _wait_out(hass)

        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.a"]

    async def test_presence_cleared_waits_the_full_wait_time(self, hass, turn_off_calls, frozen_time):
        """The template trigger's own `for:`, not just the tick's self-heal."""
        presence(hass, "binary_sensor.hall_presence", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "binary_sensor.hall_presence"]}, no_motion_wait=120
        )

        presence(hass, "binary_sensor.hall_presence", "off")
        await hass.async_block_till_done()

        frozen_time.tick(timedelta(seconds=119))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        assert turn_off_calls == [], "turned off before the Wait time was up"

        frozen_time.tick(timedelta(seconds=2))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        assert turn_off_calls and turn_off_calls[-1].data["entities"] == ["light.a"]

    async def test_presence_clearing_leaves_the_lights_on_while_a_motion_sensor_is_on(self, hass, turn_off_calls):
        presence(hass, "binary_sensor.hall_presence", "on")
        motion(hass, "binary_sensor.hall_motion", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.hall_presence", "binary_sensor.hall_motion"]},
            no_motion_wait=0,
        )

        presence(hass, "binary_sensor.hall_presence", "off")
        await hass.async_block_till_done()
        await _wait_out(hass)

        assert turn_off_calls == []

    async def test_motion_clearing_leaves_the_lights_on_while_a_presence_sensor_is_on(self, hass, turn_off_calls):
        presence(hass, "binary_sensor.hall_presence", "on")
        motion(hass, "binary_sensor.hall_motion", "on")
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.hall_presence", "binary_sensor.hall_motion"]},
            no_motion_wait=0,
        )

        motion(hass, "binary_sensor.hall_motion", "off")
        await hass.async_block_till_done()
        await _wait_out(hass)

        assert turn_off_calls == []


async def _area_room(hass) -> str:
    """A room whose area holds light.a and binary_sensor.area_presence."""
    area = ar.async_get(hass).async_get_or_create("lounge")
    ent_reg = er.async_get(hass)
    for domain, object_id in (("light", "a"), ("binary_sensor", "area_presence")):
        ent_reg.async_get_or_create(domain, "test", object_id, suggested_object_id=object_id)
        ent_reg.async_update_entity(f"{domain}.{object_id}", area_id=area.id)
    return area.id


class TestPresenceSensorsFromAreas:
    """docs/reference/blueprint.md#sensors-from-areas"""

    async def test_an_area_presence_sensor_turns_the_lights_on(self, hass, apply_lighting_calls):
        area_id = await _area_room(hass)
        presence(hass, "binary_sensor.area_presence", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"area_id": area_id})

        presence(hass, "binary_sensor.area_presence", "on")
        await hass.async_block_till_done()

        assert apply_lighting_calls and apply_lighting_calls[-1].data["entities"] == ["light.a"]

    async def test_an_area_presence_sensor_does_not_turn_the_lights_on_with_area_sensors_off(
        self, hass, apply_lighting_calls
    ):
        area_id = await _area_room(hass)
        presence(hass, "binary_sensor.area_presence", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"area_id": area_id}, use_area_sensors=False)

        presence(hass, "binary_sensor.area_presence", "on")
        await hass.async_block_till_done()

        assert apply_lighting_calls == []

    async def test_a_presence_sensor_picked_by_name_turns_the_lights_on(self, hass, apply_lighting_calls):
        area_id = await _area_room(hass)
        presence(hass, "binary_sensor.area_presence", "off")
        presence(hass, "binary_sensor.hall_presence", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"area_id": area_id, "entity_id": "binary_sensor.hall_presence"},
            use_area_sensors=False,
        )

        presence(hass, "binary_sensor.hall_presence", "on")
        await hass.async_block_till_done()

        assert apply_lighting_calls and apply_lighting_calls[-1].data["entities"] == ["light.a"]
