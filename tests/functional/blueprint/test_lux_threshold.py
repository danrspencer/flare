"""The Lux Threshold: a bright room is left dark.

The room counts as bright enough when every illuminance sensor in it reads
above the threshold; then nothing turns its lights on by itself. A manual run
(the Run button, the flare, a voice assistant) still does.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import (
    illuminance,
    light,
    motion,
    setup_room_automation,
)

ROOM = ["light.a", "binary_sensor.hall_motion"]


def lit(calls):
    """The calls that actually name a light, so an empty run doesn't count."""
    return [call for call in calls if call.data["entities"]]


class TestLuxThreshold:
    """docs/reference/blueprint.md#room"""

    async def test_every_sensor_above_the_threshold_keeps_the_lights_off(
        self, hass, apply_lighting_calls
    ):
        illuminance(hass, "sensor.lux", 500)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": [*ROOM, "sensor.lux"]}, lux_threshold=200
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []

    async def test_one_sensor_below_the_threshold_lets_the_lights_on(
        self, hass, apply_lighting_calls
    ):
        """All of them, not any of them: one dark corner is enough."""
        illuminance(hass, "sensor.lux", 500)
        illuminance(hass, "sensor.lux_low", 50)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": [*ROOM, "sensor.lux", "sensor.lux_low"]},
            lux_threshold=200,
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_a_reading_exactly_at_the_threshold_does_not_block(
        self, hass, apply_lighting_calls
    ):
        illuminance(hass, "sensor.lux", 200)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": [*ROOM, "sensor.lux"]}, lux_threshold=200
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_a_room_without_an_illuminance_sensor_still_turns_on(
        self, hass, apply_lighting_calls
    ):
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ROOM}, lux_threshold=200)

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_a_threshold_of_zero_turns_the_check_off(self, hass, apply_lighting_calls):
        illuminance(hass, "sensor.lux", 500)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": [*ROOM, "sensor.lux"]}, lux_threshold=0
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_an_unavailable_sensor_is_ignored(self, hass, apply_lighting_calls):
        """It can't say how bright the room is, so it doesn't count either way."""
        illuminance(hass, "sensor.lux", "unavailable")
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": [*ROOM, "sensor.lux"]}, lux_threshold=200
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_an_unavailable_sensor_does_not_unblock_a_bright_one(
        self, hass, apply_lighting_calls
    ):
        illuminance(hass, "sensor.lux", "unavailable")
        illuminance(hass, "sensor.lux_bright", 500)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": [*ROOM, "sensor.lux", "sensor.lux_bright"]},
            lux_threshold=200,
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []

    async def test_a_manual_run_turns_the_lights_on_anyway(self, hass, apply_lighting_calls):
        """The threshold stops the automation, not someone asking for lights."""
        illuminance(hass, "sensor.lux", 500)
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": [*ROOM, "sensor.lux"]}, lux_threshold=200
        )

        await hass.services.async_call(
            "automation", "trigger", {"entity_id": "automation.room"}, blocking=True
        )
        await hass.async_block_till_done()

        calls = lit(apply_lighting_calls)
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_lights_already_on_still_follow_the_curve(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """Blocking a turn-on must not freeze a room someone already lit."""
        illuminance(hass, "sensor.lux", 500)
        light(hass, "light.a", "on")
        light(hass, "light.b", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "sensor.lux"]},
            lux_threshold=200,
        )

        frozen_time.tick(timedelta(minutes=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        calls = lit(apply_lighting_calls)
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_a_bright_room_does_not_settle_to_its_idle_brightness(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """Idle brightness is another way a light comes on by itself."""
        illuminance(hass, "sensor.lux", 500)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": [*ROOM, "sensor.lux"]},
            lux_threshold=200,
            no_motion_wait=0,
            night_idle_brightness=20,
            day_idle_brightness=20,
            evening_idle_brightness=20,
            morning_idle_brightness=20,
        )

        frozen_time.tick(timedelta(minutes=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []

    async def test_a_scene_is_not_activated_in_a_bright_room(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        """A scene sets every light it covers, off ones included."""
        illuminance(hass, "sensor.lux", 500)
        light(hass, "light.a", "on")
        light(hass, "light.b", "off")
        hass.states.async_set(
            "scene.evening_scene",
            "2024-01-01T00:00:00+00:00",
            {"entity_id": ["light.a", "light.b"]},
        )
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "sensor.lux"]},
            evening_scene="scene.evening_scene",
            lux_threshold=200,
        )

        hass.states.async_set(
            "sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000}
        )
        await hass.async_block_till_done()

        assert scene_turn_on_calls == []
        calls = lit(apply_lighting_calls)
        assert calls and calls[-1].data["entities"] == ["light.a"]


async def _area_room(hass) -> str:
    """A room whose area holds light.a and sensor.area_lux."""
    area = ar.async_get(hass).async_get_or_create("lounge")
    ent_reg = er.async_get(hass)
    for domain, object_id in (("light", "a"), ("sensor", "area_lux")):
        ent_reg.async_get_or_create(domain, "test", object_id, suggested_object_id=object_id)
        ent_reg.async_update_entity(f"{domain}.{object_id}", area_id=area.id)
    return area.id


class TestLuxSensorsFromAreas:
    """docs/reference/blueprint.md#sensors-from-areas"""

    async def test_an_area_sensor_blocks_a_motion_turn_on(self, hass, apply_lighting_calls):
        area_id = await _area_room(hass)
        illuminance(hass, "sensor.area_lux", 500)
        light(hass, "light.a", "off")
        motion(hass, "binary_sensor.hall_motion", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"area_id": area_id, "entity_id": "binary_sensor.hall_motion"},
            lux_threshold=200,
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []

    async def test_an_area_sensor_does_not_block_with_area_sensors_off(
        self, hass, apply_lighting_calls
    ):
        area_id = await _area_room(hass)
        illuminance(hass, "sensor.area_lux", 500)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"area_id": area_id, "entity_id": "binary_sensor.hall_motion"},
            lux_threshold=200,
            use_area_sensors=False,
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_a_sensor_picked_by_name_blocks_with_area_sensors_off(
        self, hass, apply_lighting_calls
    ):
        area_id = await _area_room(hass)
        illuminance(hass, "sensor.hall_lux", 500)
        motion(hass, "binary_sensor.hall_motion", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={
                "area_id": area_id,
                "entity_id": ["binary_sensor.hall_motion", "sensor.hall_lux"],
            },
            lux_threshold=200,
            use_area_sensors=False,
        )

        motion(hass, "binary_sensor.hall_motion", "on")
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []
