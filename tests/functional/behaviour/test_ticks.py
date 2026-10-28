"""When a room re-checks its lights: on the tick of the first area it names,
spaced a gap from every other area's.

A light left on in an empty room is the probe: self-heal turns it off on
a tick and at no other time, so the moment it goes off is the moment the
room ticked. The clock starts at 19:00:02, and areas are spaced 10s apart
so every check sits well clear of a tick."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.functional.behaviour.harness import (
    at,
    occupancy,
    room_brightness,
    schedule_device,
    setup_settings,
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


async def rooms(hass: HomeAssistant, rooms_by_name: dict[str, tuple[list, dict]]) -> None:
    """One automation per room, {name: (bulbs, the rest of its target)},
    each naming its bulbs and the room's sensor."""
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
                            "room_target": {"entity_id": [b.entity_id for b in bulbs] + [ROOM_SENSOR], **target},
                            "no_motion_wait": 0,
                        },
                    },
                }
                for name, (bulbs, target) in rooms_by_name.items()
            ]
        },
    )
    await hass.async_block_till_done()


async def test_a_room_updates_on_its_areas_tick(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    """A lone area ticks on the minute."""
    areas = await setup_settings(hass, ["lounge"], options=GAP)
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": (bulbs, {"area_id": areas["lounge"]})})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 0, 55)
    assert not is_off(hass, bulbs), "nothing should tick the room between ticks"

    await at(hass, frozen_time, 19, 1, 5)
    assert is_off(hass, bulbs), "the area's tick never reached the room"


async def test_areas_tick_one_gap_apart(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    """In name order: attic on the minute, study one gap later."""
    areas = await setup_settings(hass, ["study", "attic"], options=GAP)
    attic_lamp, study_lamp = await add_bulbs("attic_lamp", "study_lamp")
    await rooms(
        hass,
        {
            "attic": ([attic_lamp], {"area_id": areas["attic"]}),
            "study": ([study_lamp], {"area_id": areas["study"]}),
        },
    )
    await switched_on_in_an_empty_room(hass, frozen_time, [attic_lamp, study_lamp])

    await at(hass, frozen_time, 19, 1, 5)
    assert (is_off(hass, [attic_lamp]), is_off(hass, [study_lamp])) == (True, False)

    await at(hass, frozen_time, 19, 1, 15)
    assert is_off(hass, [study_lamp])


async def test_a_room_follows_the_first_area_it_names(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    """The lamp sits in the attic, but the room names the study first."""
    areas = await setup_settings(hass, ["study", "attic"], options=GAP)
    (lamp,) = await add_bulbs("lamp", area_id=areas["attic"])
    await rooms(hass, {"lamp": ([lamp], {"area_id": [areas["study"], areas["attic"]]})})
    await switched_on_in_an_empty_room(hass, frozen_time, [lamp])

    await at(hass, frozen_time, 19, 1, 5)
    assert not is_off(hass, [lamp]), "the attic's tick shouldn't reach a room following the study"

    await at(hass, frozen_time, 19, 1, 15)
    assert is_off(hass, [lamp])


async def test_a_new_area_starts_ticking(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    """Areas are ticked as the area registry has them, not as it was at setup."""
    await setup_settings(hass, [], options=GAP)
    porch = ar.async_get(hass).async_get_or_create("porch").id
    bulbs = await add_bulbs("porch_lamp", area_id=porch)
    await rooms(hass, {"porch": (bulbs, {"area_id": porch})})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 1, 5)
    assert is_off(hass, bulbs)


async def test_the_interval_is_set_on_the_entry(hass: HomeAssistant, add_bulbs, frozen_time) -> None:
    areas = await setup_settings(hass, ["lounge"], options={**GAP, "tick_interval": 2})
    bulbs = await add_bulbs("lounge_lamp", area_id=areas["lounge"])
    await rooms(hass, {"lounge": (bulbs, {"area_id": areas["lounge"]})})
    await switched_on_in_an_empty_room(hass, frozen_time, bulbs)

    await at(hass, frozen_time, 19, 1, 5)
    assert not is_off(hass, bulbs), "19:01 isn't on a two-minute boundary"

    await at(hass, frozen_time, 19, 2, 5)
    assert is_off(hass, bulbs)


async def test_a_tick_is_a_plain_event_naming_the_area(hass: HomeAssistant, frozen_time) -> None:
    """Not an entity, so ticks never show in Activity, history or the logbook."""
    areas = await setup_settings(hass, ["lounge"])
    ticks: list = []
    hass.bus.async_listen("flare_tick", ticks.append)

    await at(hass, frozen_time, 19, 1, 1)

    assert [t.data for t in ticks] == [{"area_id": areas["lounge"]}]
    flare_events = [e.entity_id for e in er.async_get(hass).entities.values() if e.platform == "flare" and e.domain == "event"]
    assert [e for e in flare_events if "tick" in e] == []
