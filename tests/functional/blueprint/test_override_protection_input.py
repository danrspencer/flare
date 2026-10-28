"""Override Protection, and which tick a room follows: its first area's, or
on the minute without one. docs/reference/blueprint.md#turning-override-protection-off"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import light, setup_room_automation


async def _a_minute_later(hass) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()


def _area_light(hass, entity_id: str, area_id: str) -> None:
    registry = er.async_get(hass)
    created = registry.async_get_or_create("light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1])
    registry.async_update_entity(created.entity_id, area_id=area_id)
    light(hass, entity_id, "on", brightness=190, color_temp_kelvin=4000)


async def test_with_protection_on_writes_name_the_automation_and_its_lights(hass, apply_lighting_calls):
    light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
    light(hass, "light.b", "off")
    await hass.async_block_till_done()
    await setup_room_automation(hass, room_target={"entity_id": ["light.a", "light.b"]})

    await _a_minute_later(hass)

    assert apply_lighting_calls[-1].data["room_id"] == "automation.room"
    assert sorted(apply_lighting_calls[-1].data["room_entities"]) == ["light.a", "light.b"]


async def test_with_protection_off_it_tracks_nothing(hass, apply_lighting_calls):
    light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
    await hass.async_block_till_done()
    await setup_room_automation(hass, room_target={"entity_id": "light.a"}, override_protection=False)

    await _a_minute_later(hass)

    assert apply_lighting_calls and apply_lighting_calls[-1].data["entities"] == ["light.a"]
    assert apply_lighting_calls[-1].data["room_id"] is None


async def test_a_room_naming_no_area_ticks_on_the_minute(hass, apply_lighting_calls):
    light(hass, "light.a", "on", brightness=190, color_temp_kelvin=4000)
    await hass.async_block_till_done()
    await setup_room_automation(hass, room_target={"entity_id": "light.a"}, area_ticks=False)

    await _a_minute_later(hass)

    assert apply_lighting_calls


async def test_a_room_naming_an_area_ticks_only_on_its_areas_tick(hass, apply_lighting_calls):
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


async def test_a_room_naming_several_areas_follows_the_first(hass, apply_lighting_calls):
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


async def test_with_protection_off_lights_handed_to_a_scene_have_no_claims_to_release(
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
        override_protection=False,
    )

    hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
    await hass.async_block_till_done()

    assert scene_turn_on_calls, "the scene still takes its lights"
    assert claims_clear_calls == []
