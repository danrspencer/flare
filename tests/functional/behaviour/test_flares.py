"""Flares: a light over the room's automation, for voice assistants,
HomeKit and dashboards, asserted on the state the bulbs end up in."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.flare.const import DOMAIN, TURN_OFF_LIGHT
from tests.functional.behaviour.harness import (
    CURVE_BRIGHTNESS,
    HALL_BULBS,
    HALL_SENSOR,
    ZONE,
    add_flare,
    let_time_pass,
    occupancy,
    room_brightness,
    zone_device,
)

HAND_SET = 40


async def _turn_on(hass: HomeAssistant, flare: str, **data) -> None:
    await hass.services.async_call("light", "turn_on", {"entity_id": flare, **data}, blocking=True)
    await hass.async_block_till_done()


async def _turn_off(hass: HomeAssistant, flare: str) -> None:
    await hass.services.async_call("light", "turn_off", {"entity_id": flare}, blocking=True)
    await hass.async_block_till_done()


async def _room(hass, add_bulbs, setup_room, zone, *, occupied: bool):
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR])
    if occupied:
        occupancy(hass, HALL_SENSOR, "on")
        await hass.async_block_till_done()
    return bulbs


async def test_turning_a_flare_on_lights_the_room_the_way_its_automation_would(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    """No motion, so only the automation's manual run can light it."""
    bulbs = await _room(hass, add_bulbs, setup_room, zone, occupied=False)
    flare = await add_flare(hass)
    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}

    await _turn_on(hass, flare)

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    assert hass.states.get(flare).state == "on"


async def test_a_transition_alone_still_runs_the_automation(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone, **{name: {"supports_transition": True} for name in HALL_BULBS})
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR])
    flare = await add_flare(hass)

    await _turn_on(hass, flare, transition=2)

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}


async def test_a_flare_turned_on_with_a_brightness_sets_every_light_and_the_room_leaves_it(
    hass: HomeAssistant, add_bulbs, setup_room, zone, frozen_time
) -> None:
    bulbs = await _room(hass, add_bulbs, setup_room, zone, occupied=True)
    flare = await add_flare(hass)

    await _turn_on(hass, flare, brightness=HAND_SET)
    await let_time_pass(hass, frozen_time, 61)

    assert room_brightness(hass, bulbs) == {b.entity_id: HAND_SET for b in bulbs}


async def test_turning_a_flare_on_again_hands_the_room_back(
    hass: HomeAssistant, add_bulbs, setup_room, zone, frozen_time
) -> None:
    bulbs = await _room(hass, add_bulbs, setup_room, zone, occupied=True)
    flare = await add_flare(hass)
    await _turn_on(hass, flare, brightness=HAND_SET)
    await let_time_pass(hass, frozen_time, 61)
    assert room_brightness(hass, bulbs) == {b.entity_id: HAND_SET for b in bulbs}

    await _turn_on(hass, flare)

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}


async def test_a_flare_turned_off_turns_the_room_off_and_motion_lights_it_again(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    bulbs = await _room(hass, add_bulbs, setup_room, zone, occupied=True)
    flare = await add_flare(hass)

    await _turn_off(hass, flare)
    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}
    assert hass.states.get(flare).state == "off"

    occupancy(hass, HALL_SENSOR, "off")
    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}


async def _statuses(hass: HomeAssistant, entities: list[str]) -> dict[str, str]:
    response = await hass.services.async_call(
        DOMAIN,
        "claims_check",
        {"entities": entities, "zone_device_id": zone_device(hass, ZONE)},
        blocking=True,
        return_response=True,
    )
    return {e: r["status"] for e, r in response["results"].items()}


async def _room_with_a_light_of_its_own(hass, add_bulbs, setup_room, zone):
    """A room whose zone also drives a lamp the automation doesn't, so the
    zone isn't dark when the flare turns off and its claims stay."""
    bulbs = await add_bulbs(*HALL_BULBS, "hall_extra", area_id=zone)
    *room, extra = bulbs
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=room, occupancy_sensors=[HALL_SENSOR])
    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN,
        "apply_lighting",
        {
            "entities": [extra.entity_id],
            "brightness": CURVE_BRIGHTNESS,
            "color_temp_kelvin": 3200,
            "transition": 0,
            "zone_device_id": zone_device(hass, ZONE),
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    return room


async def test_a_flare_turns_off_through_flare_so_the_zone_knows_it_was_ours(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    room = await _room_with_a_light_of_its_own(hass, add_bulbs, setup_room, zone)
    flare = await add_flare(hass)

    await _turn_off(hass, flare)

    assert set((await _statuses(hass, [b.entity_id for b in room])).values()) == {"controlled"}


async def test_a_flare_set_to_light_turn_off_leaves_the_zone_reading_it_as_someone_elses(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    room = await _room_with_a_light_of_its_own(hass, add_bulbs, setup_room, zone)
    flare = await add_flare(hass, turn_off=TURN_OFF_LIGHT)

    await _turn_off(hass, flare)

    assert room_brightness(hass, room) == {b.entity_id: "off" for b in room}
    assert set((await _statuses(hass, [b.entity_id for b in room])).values()) == {"overridden"}


async def _area_room(hass, add_bulbs, setup_room, zone):
    """The room's lights named by area, with the automation in that area too."""
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=[], room_target={"area_id": zone, "entity_id": [HALL_SENSOR]})
    er.async_get(hass).async_update_entity("automation.room", area_id=zone)
    return bulbs


async def test_a_new_flare_starts_in_its_automations_area(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    await _area_room(hass, add_bulbs, setup_room, zone)

    flare = await add_flare(hass)

    device_id = er.async_get(hass).async_get(flare).device_id
    assert dr.async_get(hass).async_get(device_id).area_id == zone


async def test_a_flare_taken_out_of_its_area_stays_out(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    """The area is only set when the flare is created; after that it's the user's."""
    await _area_room(hass, add_bulbs, setup_room, zone)
    flare = await add_flare(hass)
    devices = dr.async_get(hass)
    device_id = er.async_get(hass).async_get(flare).device_id
    devices.async_update_device(device_id, area_id=None)

    (entry,) = [e for e in hass.config_entries.async_entries(DOMAIN) if e.title == "Flares"]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert devices.async_get(device_id).area_id is None


async def test_a_flare_in_its_rooms_area_is_not_one_of_the_rooms_lights(
    hass: HomeAssistant, add_bulbs, setup_room, zone, frozen_time
) -> None:
    """Were it, the room's own tick would send it the curve, and it would
    pass that on to every light as a hand-set override."""
    bulbs = await _area_room(hass, add_bulbs, setup_room, zone)
    flare = await add_flare(hass)
    assert flare not in hass.states.get(flare).attributes["entity_id"]
    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()

    await _turn_on(hass, flare, brightness=HAND_SET)
    await _turn_on(hass, flare)
    await let_time_pass(hass, frozen_time, 61)

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}


async def test_flares_services_never_drive_a_flare(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    bulbs = await _room(hass, add_bulbs, setup_room, zone, occupied=False)
    flare = await add_flare(hass)

    await hass.services.async_call(
        DOMAIN,
        "apply_lighting",
        {"entities": [flare], "brightness": HAND_SET, "color_temp_kelvin": 3200, "transition": 0},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}


async def test_a_light_added_to_the_room_joins_its_flare(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    bulbs = await _area_room(hass, add_bulbs, setup_room, zone)
    flare = await add_flare(hass)
    newcomer, *_ = bulbs
    er.async_get(hass).async_update_entity(newcomer.entity_id, area_id=None)
    await hass.async_block_till_done()
    assert newcomer.entity_id not in hass.states.get(flare).attributes["entity_id"]

    er.async_get(hass).async_update_entity(newcomer.entity_id, area_id=zone)
    await hass.async_block_till_done()

    assert newcomer.entity_id in hass.states.get(flare).attributes["entity_id"]


async def test_a_flare_whose_automation_is_gone_is_unavailable(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    await _room(hass, add_bulbs, setup_room, zone, occupied=False)
    flare = await add_flare(hass)
    assert hass.states.get(flare).state != "unavailable"

    er.async_get(hass).async_remove("automation.room")
    await hass.async_block_till_done()

    assert hass.states.get(flare).state == "unavailable"
