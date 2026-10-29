"""Ticks from the schedule sensor, the area's tick and Additional Triggers:
which tick a room follows is its first area's, or on the minute without one."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import (
    add_schedule,
    effective,
    light,
    occupancy,
    setup_room_automation,
)
from tests.support import load_blueprint


async def _a_minute_later(hass) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()


def _area_light(hass, entity_id: str, area_id: str) -> None:
    registry = er.async_get(hass)
    created = registry.async_get_or_create("light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1])
    registry.async_update_entity(created.entity_id, area_id=area_id)
    light(hass, entity_id, "on", brightness=190, color_temp_kelvin=4000)


class TestAdaptiveScheduleAndTransitions:
    """docs/reference/blueprint.md#transitions"""

    async def test_an_unavailable_sensor_skips_the_tick_instead_of_erroring(self, hass, apply_lighting_calls):
        """apply_lighting requires both values, so an unavailable sensor would
        otherwise fail every tick, indefinitely and unnoticed."""
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        hass.states.async_set("sensor.test_adaptive", "unavailable", {})
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls == []

    async def test_a_schedule_with_no_sensor_skips_the_tick(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": "light.a"}, schedule=add_schedule(hass, sensor=None, slug="empty")
        )

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls == []

    async def test_periodic_tick_updates_an_already_on_light(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        # Same phase, attributes only: only the tick picks this up.
        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]
        # The sensor's values reach apply_lighting (rgb_color None: this sensor
        # doesn't publish it).
        assert effective(calls[-1], "light.a") == 210
        assert calls[-1].data["color_temp_kelvin"] == 4000
        assert calls[-1].data["rgb_color"] is None

    async def test_a_flat_curve_still_gets_a_tick(self, hass, apply_lighting_calls):
        """On a flat stretch the sensor emits state_reported, not state_changed,
        so only the tick guarantees an update."""
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        hass.states.async_set("sensor.test_adaptive", "Morning", {"brightness": 255, "color_temp": 6667})
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})
        apply_lighting_calls.clear()

        # No sensor write: anything that fires is the Tick.
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
        await hass.async_block_till_done()

        assert apply_lighting_calls, "a flat curve must still produce a tick"
        assert apply_lighting_calls[-1].data["entities"] == ["light.a"]

    async def test_tick_uses_the_background_transition_duration(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass, room_target={"entity_id": "light.a"}, background_transition=45, motion_on_transition=2
        )

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls[-1].data["transition"] == 45

    async def test_motion_on_uses_the_motion_on_transition_duration(self, hass, apply_lighting_calls):
        occupancy(hass, "binary_sensor.occ", "off")
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": ["light.a", "binary_sensor.occ"]},
            background_transition=45,
            motion_on_transition=2,
        )

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls[-1].data["transition"] == 2

    async def test_attribute_only_same_phase_update_does_not_call_apply_lighting(
        self, hass, apply_lighting_calls
    ):
        """The trigger's `to:` filter drops it before the automation runs."""
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})
        apply_lighting_calls.clear()

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 220, "color_temp": 4000})
        await hass.async_block_till_done()

        assert apply_lighting_calls == []

    async def test_genuine_phase_transition_calls_apply_lighting(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})
        apply_lighting_calls.clear()

        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]

    async def test_nothing_delays_the_action_before_it_decides(self):
        """Variables render at trigger time, so a delay acts on a stale decision:
        a light switched off by hand during it would be relit. Override
        protection can't catch that (the dark room released its claims), so
        the blueprint must not delay at all."""
        blueprint = load_blueprint()

        def delays(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "delay":
                        yield value
                    yield from delays(value)
            elif isinstance(node, list):
                for item in node:
                    yield from delays(item)

        assert list(delays(blueprint["action"])) == []

    async def test_a_schedules_first_phase_counts_as_a_phase_change(self, hass, apply_lighting_calls):
        """A new schedule has no previous phase, which must still count."""
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(
            hass,
            room_target={"entity_id": "light.a"},
            schedule=add_schedule(hass, sensor="sensor.brand_new_adaptive", slug="brand_new"),
        )

        hass.states.async_set("sensor.brand_new_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]


class TestAreaTicks:
    """docs/reference/blueprint.md#when-the-room-updates"""

    async def test_a_room_naming_no_area_ticks_on_the_minute(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"}, area_ticks=False)

        await _a_minute_later(hass)

        assert apply_lighting_calls

    async def test_a_room_naming_an_area_ticks_only_on_its_areas_tick(self, hass, apply_lighting_calls):
        kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
        _area_light(hass, "light.k", kitchen.id)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"area_id": kitchen.id}, area_ticks=False)

        await _a_minute_later(hass)
        assert apply_lighting_calls == [], "no time_pattern for a room with an area"

        hass.bus.async_fire("flare_tick", {"area_id": "somewhere_else"})
        await hass.async_block_till_done()
        assert apply_lighting_calls == []

        hass.bus.async_fire("flare_tick", {"area_id": kitchen.id})
        await hass.async_block_till_done()
        assert apply_lighting_calls

    async def test_a_room_naming_several_areas_follows_the_first(self, hass, apply_lighting_calls):
        """However the picker stores them: a list here."""
        kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
        hall = ar.async_get(hass).async_get_or_create("Hall")
        _area_light(hass, "light.k", kitchen.id)
        _area_light(hass, "light.h", hall.id)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"area_id": [kitchen.id, hall.id]}, area_ticks=False)

        hass.bus.async_fire("flare_tick", {"area_id": hall.id})
        await hass.async_block_till_done()
        assert apply_lighting_calls == []

        hass.bus.async_fire("flare_tick", {"area_id": kitchen.id})
        await hass.async_block_till_done()
        assert apply_lighting_calls


class TestRgbColour:
    """docs/reference/blueprint.md#prefer-rgb-during"""

    async def test_prefer_rgb_color_is_true_only_during_a_configured_phase(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"}, rgb_phases=["Day"])

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls[-1].data["prefer_rgb_color"] is True

    async def test_prefer_rgb_color_is_false_outside_configured_phases(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls[-1].data["prefer_rgb_color"] is False


class TestAdditionalTriggers:
    """docs/reference/blueprint.md#additional-triggers"""

    async def test_extra_trigger_entity_change_causes_immediate_reevaluation(self, hass, apply_lighting_calls):
        light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
        hass.states.async_set("binary_sensor.dependency", "off")
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": "light.a"}, extra_triggers=["binary_sensor.dependency"]
        )

        hass.states.async_set("binary_sensor.dependency", "on")
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]
