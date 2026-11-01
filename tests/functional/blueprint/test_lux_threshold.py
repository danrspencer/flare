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
    occupancy,
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

    async def test_a_non_numeric_sensor_does_not_unblock_a_bright_one(
        self, hass, apply_lighting_calls
    ):
        illuminance(hass, "sensor.lux", "dusk")
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
            "sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp_kelvin": 3000}
        )
        await hass.async_block_till_done()

        assert scene_turn_on_calls == []
        assert lit(apply_lighting_calls) == []

    async def test_a_lit_scene_stays_the_scenes_once_the_room_is_bright(
        self, hass, apply_lighting_calls, scene_turn_on_calls, frozen_time
    ):
        """Its lights aren't taken onto the curve when the sun comes out."""
        illuminance(hass, "sensor.lux", 500)
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        hass.states.async_set(
            "scene.evening_scene",
            "2024-01-01T00:00:00+00:00",
            {"entity_id": ["light.a", "light.b"]},
        )
        hass.states.async_set(
            "sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp_kelvin": 3000}
        )
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "sensor.lux"]},
            evening_scene="scene.evening_scene",
            lux_threshold=200,
        )

        frozen_time.tick(timedelta(minutes=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []



    async def test_a_phase_change_moves_a_lit_scene_on_while_it_is_bright(
        self, hass, scene_turn_on_calls
    ):
        """Every light it covers is already on, so it can't light anything."""
        illuminance(hass, "sensor.lux", 500)
        light(hass, "light.a", "on")
        light(hass, "light.b", "on")
        for scene in ("scene.evening_scene", "scene.night_scene"):
            hass.states.async_set(
                scene, "2024-01-01T00:00:00+00:00", {"entity_id": ["light.a", "light.b"]}
            )
        hass.states.async_set(
            "sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp_kelvin": 3000}
        )
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "light.b", "sensor.lux"]},
            evening_scene="scene.evening_scene",
            night_scene="scene.night_scene",
            lux_threshold=200,
        )

        hass.states.async_set(
            "sensor.test_adaptive", "Night", {"brightness": 80, "color_temp_kelvin": 2700}
        )
        await hass.async_block_till_done()

        assert scene_turn_on_calls[-1].data["entity_id"] == ["scene.night_scene"]

class TestLuxThresholdAtDusk:
    """docs/reference/blueprint.md#lux-threshold"""

    async def _bright_room_with_someone_in_it(self, hass, **inputs):
        illuminance(hass, "sensor.lux", 500)
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ", "sensor.lux"]},
            lux_threshold=200,
            **inputs,
        )
        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

    async def test_the_lights_come_on_when_it_gets_dark_with_someone_there(
        self, hass, apply_lighting_calls
    ):
        await self._bright_room_with_someone_in_it(hass)
        assert lit(apply_lighting_calls) == []

        illuminance(hass, "sensor.lux", 20)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_a_sensor_cleared_within_the_wait_time_still_counts_as_someone_there(
        self, hass, apply_lighting_calls
    ):
        """A PIR goes clear while someone sits still."""
        await self._bright_room_with_someone_in_it(hass, no_motion_wait=600)
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()

        illuminance(hass, "sensor.lux", 20)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_an_empty_room_stays_dark_when_it_gets_dark(self, hass, apply_lighting_calls):
        await self._bright_room_with_someone_in_it(hass, no_motion_wait=0)
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()

        illuminance(hass, "sensor.lux", 20)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []

    async def test_a_room_without_an_occupancy_sensor_stays_dark_when_it_gets_dark(
        self, hass, apply_lighting_calls
    ):
        illuminance(hass, "sensor.lux", 500)
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": ["light.a", "sensor.lux"]}, lux_threshold=200
        )

        illuminance(hass, "sensor.lux", 20)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls) == []

    async def test_one_sensor_getting_dark_is_enough(self, hass, apply_lighting_calls):
        illuminance(hass, "sensor.lux", 500)
        illuminance(hass, "sensor.lux_window", 900)
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={
                "entity_id": ["light.a", "binary_sensor.occ", "sensor.lux", "sensor.lux_window"]
            },
            lux_threshold=200,
        )

        illuminance(hass, "sensor.lux", 20)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_an_area_sensor_getting_dark_lights_the_room(self, hass, apply_lighting_calls):
        area_id = await _area_room(hass)
        illuminance(hass, "sensor.area_lux", 500)
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"area_id": area_id, "entity_id": "binary_sensor.occ"},
            lux_threshold=200,
        )

        illuminance(hass, "sensor.area_lux", 20)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_with_area_sensors_off_only_a_picked_sensor_getting_dark_counts(
        self, hass, apply_lighting_calls
    ):
        """An area sensor that's already dark doesn't stand in for the picked one."""
        area_id = await _area_room(hass)
        illuminance(hass, "sensor.area_lux", 20)
        illuminance(hass, "sensor.hall_lux", 500)
        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={
                "area_id": area_id,
                "entity_id": ["binary_sensor.occ", "sensor.hall_lux"],
            },
            lux_threshold=200,
            use_area_sensors=False,
        )
        assert lit(apply_lighting_calls) == []

        illuminance(hass, "sensor.hall_lux", 20)
        await hass.async_block_till_done()

        assert lit(apply_lighting_calls)[-1].data["entities"] == ["light.a"]

    async def test_a_scene_held_off_while_bright_is_activated_at_dusk(
        self, hass, scene_turn_on_calls
    ):
        hass.states.async_set(
            "scene.evening_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.a"]}
        )
        hass.states.async_set(
            "sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp_kelvin": 3000}
        )
        await self._bright_room_with_someone_in_it(hass, evening_scene="scene.evening_scene")
        assert scene_turn_on_calls == []

        illuminance(hass, "sensor.lux", 20)
        await hass.async_block_till_done()

        assert scene_turn_on_calls[-1].data["entity_id"] == ["scene.evening_scene"]

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
