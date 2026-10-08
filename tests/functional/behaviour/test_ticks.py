"""When a room re-checks its lights: on the tick of the zone it picks,
spaced a gap from every other zone's.

A light left on in an empty room is the probe: self-heal turns it off on
a tick and at no other time, so the moment it goes off is the moment the
room ticked. The clock starts at 19:00:02, and zones are spaced 10s apart
so every check sits well clear of a tick."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.functional.behaviour.harness import (
    at,
    occupancy,
    room_brightness,
    schedule_device,
    setup_zones,
    zone_device,
)
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


async def rooms(hass: HomeAssistant, rooms_by_name: dict[str, tuple[list, str]]) -> None:
    """One automation per room, {name: (bulbs, zone device)}, each naming its
    bulbs and the room's sensor."""
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
                        "input": {
                            "schedule": schedule_device(hass),
                            "room_target": {"entity_id": [b.entity_id for b in bulbs] + [ROOM_SENSOR]},
                            "zone": zone,
                            "no_motion_wait": 0,
                        },
                    },
                }
                for name, (bulbs, zone) in rooms_by_name.items()
            ]
        },
    )
    await hass.async_block_till_done()


async def test_a_room_updates_on_its_zones_tick(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    """A lone zone ticks on the minute."""
    areas = await setup_zones(hass, ["lounge"], options=GAP)
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": (bulbs, zone_device(hass, "lounge"))})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 0, 55)
    assert not is_off(hass, bulbs), "nothing should tick the room between Ticks"

    await at(hass, frozen_time, 19, 1, 5)
    assert is_off(hass, bulbs), "the zone's Tick never reached the room"


async def test_zones_tick_one_gap_apart(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    """In title order: attic on the minute, study one gap later."""
    await setup_zones(hass, ["study", "attic"], options=GAP)
    attic_lamp, study_lamp = await add_bulbs("attic_lamp", "study_lamp")
    await rooms(
        hass,
        {
            "attic": ([attic_lamp], zone_device(hass, "attic")),
            "study": ([study_lamp], zone_device(hass, "study")),
        },
    )
    await switched_on_in_an_empty_room(hass, frozen_time, [attic_lamp, study_lamp])

    await at(hass, frozen_time, 19, 1, 5)
    assert (is_off(hass, [attic_lamp]), is_off(hass, [study_lamp])) == (True, False)

    await at(hass, frozen_time, 19, 1, 15)
    assert is_off(hass, [study_lamp])


async def test_the_picked_zone_wins_over_the_area_the_lights_are_in(
    hass: HomeAssistant, add_bulbs, frozen_time
) -> None:
    """The lamp sits in the attic, but the room picks the study's zone."""
    areas = await setup_zones(hass, ["study", "attic"], options=GAP)
    (lamp,) = await add_bulbs("lamp", area_id=areas["attic"])
    await rooms(hass, {"lamp": ([lamp], zone_device(hass, "study"))})
    await switched_on_in_an_empty_room(hass, frozen_time, [lamp])

    await at(hass, frozen_time, 19, 1, 5)
    assert not is_off(hass, [lamp]), "the attic's Tick shouldn't reach a room in the study's zone"

    await at(hass, frozen_time, 19, 1, 15)
    assert is_off(hass, [lamp])


async def test_the_interval_is_set_on_the_entry(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    areas = await setup_zones(hass, ["lounge"], options={**GAP, "tick_interval": 2})
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": (bulbs, zone_device(hass, "lounge"))})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 1, 5)
    assert not is_off(hass, bulbs), "19:01 isn't on a two-minute boundary"

    await at(hass, frozen_time, 19, 2, 5)
    assert is_off(hass, bulbs)


async def test_a_tick_is_a_plain_event_naming_the_zones_device(hass: HomeAssistant, frozen_time) -> None:
    """Not an entity, so ticks never show in Activity, history or the logbook."""
    await setup_zones(hass, ["lounge"])
    device = zone_device(hass, "lounge")
    ticks: list = []
    hass.bus.async_listen("flare_tick", ticks.append)

    await at(hass, frozen_time, 19, 1, 1)

    assert [t.data for t in ticks] == [{"device_id": device}]
    flare_events = [e.entity_id for e in er.async_get(hass).entities.values() if e.platform == "flare" and e.domain == "event"]
    assert [e for e in flare_events if "tick" in e] == []


