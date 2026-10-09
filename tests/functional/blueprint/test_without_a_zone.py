"""A room with Zone left empty: no override protection, and a tick on the
minute in place of the zone's. docs/reference/blueprint.md#without-a-zone"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import add_zone, light, setup_room_automation


async def _a_minute_later(hass) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()


async def test_it_ticks_on_the_minute_and_tracks_nothing(hass, apply_lighting_calls):
    light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
    await hass.async_block_till_done()
    await setup_room_automation(hass, room_target={"entity_id": "light.a"}, zoned=False)

    await _a_minute_later(hass)

    assert apply_lighting_calls and apply_lighting_calls[-1].data["entities"] == ["light.a"]
    assert apply_lighting_calls[-1].data["zone_device_id"] is None


async def test_a_room_with_a_zone_ticks_only_on_the_zones_tick(hass, apply_lighting_calls):
    light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
    await hass.async_block_till_done()
    await setup_room_automation(hass, room_target={"entity_id": "light.a"}, zone=add_zone(hass, ticks=False))

    await _a_minute_later(hass)

    assert apply_lighting_calls == []


async def test_lights_handed_to_a_scene_have_no_claims_to_release(
    hass, apply_lighting_calls, scene_turn_on_calls, claims_clear_calls
):
    light(hass, "light.covered", "on")
    light(hass, "light.uncovered", "on")
    hass.states.async_set("scene.evening_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.covered"]})
    await hass.async_block_till_done()
    await setup_room_automation(
        hass,
        room_target={"entity_id": ["light.covered", "light.uncovered"]},
        evening_scene="scene.evening_scene",
        zoned=False,
    )

    hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
    await hass.async_block_till_done()

    assert scene_turn_on_calls, "the scene still takes its lights"
    assert claims_clear_calls == []
