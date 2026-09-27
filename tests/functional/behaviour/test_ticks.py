"""When a room re-checks its lights: on its zone's Tick, spaced from every
other zone's, or on the minute for a room that doesn't reach a Tick.

A light left on in an empty room is the probe: self-heal turns it off on
a tick and at no other time, so the moment it goes off is the moment the
room ticked. The clock starts at 19:00:02, and zones are spaced 10s apart
so every check sits well clear of a tick."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.functional.behaviour.harness import SCHEDULE_SENSOR, at, occupancy, room_brightness, setup_zones
from tests.support import BLUEPRINT_PATH

ROOM_SENSOR = "binary_sensor.tick_room_occupancy"
GAP = {"tick_gap": 10}


async def switched_on_in_an_empty_room(hass: HomeAssistant, frozen, bulbs) -> None:
    """At 19:00:30, past the first minute's ticks."""
    occupancy(hass, ROOM_SENSOR, "off")
    await at(hass, frozen, 19, 0, 30)
    await hass.services.async_call("light", "turn_on", {"entity_id": [b.entity_id for b in bulbs]}, blocking=True)
    await hass.async_block_till_done()
    assert not any(is_off(hass, [b]) for b in bulbs)


def is_off(hass: HomeAssistant, bulbs) -> bool:
    return all(v == "off" for v in room_brightness(hass, bulbs).values())


async def rooms(hass: HomeAssistant, targets: dict[str, dict]) -> None:
    """One automation per room from the blueprint, keyed by name."""
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "id": name,
                    "alias": name,
                    "use_blueprint": {
                        "path": BLUEPRINT_PATH,
                        "input": {"adaptive_sensor": SCHEDULE_SENSOR, "room_target": target, "no_motion_wait": 0},
                    },
                }
                for name, target in targets.items()
            ]
        },
    )
    await hass.async_block_till_done()


async def test_a_room_reaching_its_zones_tick_checks_after_the_minute_not_on_it(
    hass: HomeAssistant, add_bulbs, frozen_time
) -> None:
    areas = await setup_zones(hass, ["lounge"], options=GAP)
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": {"area_id": [areas["lounge"]], "entity_id": [ROOM_SENSOR]}})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 1, 5)
    assert not is_off(hass, bulbs), "the minute's time pattern should stand aside for the zone's Tick"

    await at(hass, frozen_time, 19, 1, 15)
    assert is_off(hass, bulbs), "the zone's Tick, one gap past the minute, never reached the room"


async def test_a_room_naming_only_its_lights_still_checks_on_the_minute(
    hass: HomeAssistant, add_bulbs, frozen_time
) -> None:
    """Its target doesn't reach the zone's Tick, so the time pattern stays."""
    areas = await setup_zones(hass, ["lounge"], options=GAP)
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": {"entity_id": [bulbs[0].entity_id, ROOM_SENSOR]}})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 1, 5)

    assert is_off(hass, bulbs)


async def test_naming_the_zones_tick_moves_a_room_onto_it(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    areas = await setup_zones(hass, ["lounge"], options=GAP)
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": {"entity_id": [bulbs[0].entity_id, ROOM_SENSOR, "event.lounge_flare_tick"]}})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 1, 5)
    assert not is_off(hass, bulbs)

    await at(hass, frozen_time, 19, 1, 15)
    assert is_off(hass, bulbs)


async def test_zones_tick_one_gap_apart(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    """In title order: attic one gap past the minute, study two."""
    areas = await setup_zones(hass, ["study", "attic"], options=GAP)
    attic_lamp, study_lamp = await add_bulbs("attic_lamp", "study_lamp")
    registry = er.async_get(hass)
    registry.async_update_entity(attic_lamp.entity_id, area_id=areas["attic"])
    registry.async_update_entity(study_lamp.entity_id, area_id=areas["study"])
    await rooms(hass, {zone: {"area_id": [areas[zone]], "entity_id": [ROOM_SENSOR]} for zone in ("attic", "study")})
    await switched_on_in_an_empty_room(hass, frozen_time, [attic_lamp, study_lamp])

    await at(hass, frozen_time, 19, 1, 15)
    assert (is_off(hass, [attic_lamp]), is_off(hass, [study_lamp])) == (True, False)

    await at(hass, frozen_time, 19, 1, 25)
    assert is_off(hass, [study_lamp])


async def test_the_interval_is_set_on_the_entry(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    areas = await setup_zones(hass, ["lounge"], options={**GAP, "tick_interval": 2})
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": {"area_id": [areas["lounge"]], "entity_id": [ROOM_SENSOR]}})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 1, 15)
    assert not is_off(hass, bulbs), "19:01 isn't on a two-minute boundary"

    await at(hass, frozen_time, 19, 2, 15)
    assert is_off(hass, bulbs)
