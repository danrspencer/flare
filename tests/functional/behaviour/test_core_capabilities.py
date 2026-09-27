"""What FLARE does in an ordinary room on an ordinary day, asserted on
the state the bulbs end up in. Every test runs untracked and tracked."""

from homeassistant.core import HomeAssistant

from tests.functional.behaviour.harness import (
    CURVE_BRIGHTNESS,
    HALL_BULBS,
    HALL_SENSOR,
    NIGHT_BRIGHTNESS,
    let_time_pass,
    move_to_phase,
    occupancy,
    room_brightness,
)

# Past the blueprint's Wait time check, with no_motion_wait=0.
PAST_THE_WAIT = 120
SECOND_SENSOR = "binary_sensor.hall_doorway_occupancy"


async def lit_room(hass, add_bulbs, setup_room, tracking_scope, **inputs):
    """An occupied room at the curve."""
    bulbs = await add_bulbs(*HALL_BULBS, area_id=tracking_scope)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR], **inputs)
    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()
    return bulbs



async def test_it_turns_the_lights_on_when_a_room_becomes_occupied(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=tracking_scope)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR])

    assert room_brightness(hass, bulbs) == {bulb.entity_id: "off" for bulb in bulbs}, (
        "the room should start dark, or this test proves nothing"
    )

    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()

    assert room_brightness(hass, bulbs) == {
        bulb.entity_id: CURVE_BRIGHTNESS for bulb in bulbs
    }, "occupancy did not light the whole room to the curve"


async def test_the_room_ends_up_dark_once_it_is_empty(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """The outcome only: motion_off or self-heal may deliver it."""
    bulbs = await lit_room(hass, add_bulbs, setup_room, tracking_scope, no_motion_wait=0)
    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}

    occupancy(hass, HALL_SENSOR, "off")
    await hass.async_block_till_done()
    await let_time_pass(hass, frozen_time, PAST_THE_WAIT)

    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}, (
        "the room emptied but the lights stayed on"
    )


async def test_one_sensors_wait_running_out_does_not_empty_a_room_another_saw_motion_in(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """Each sensor's Wait time runs out on its own; the room is only empty
    once they all have."""
    bulbs = await add_bulbs(*HALL_BULBS, area_id=tracking_scope)
    occupancy(hass, HALL_SENSOR, "off")
    occupancy(hass, SECOND_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR, SECOND_SENSOR], no_motion_wait=300)
    occupancy(hass, HALL_SENSOR, "on")
    occupancy(hass, SECOND_SENSOR, "on")
    await hass.async_block_till_done()
    lit = {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    assert room_brightness(hass, bulbs) == lit

    occupancy(hass, HALL_SENSOR, "off")
    await let_time_pass(hass, frozen_time, 100)
    occupancy(hass, SECOND_SENSOR, "off")
    await let_time_pass(hass, frozen_time, 201)

    assert room_brightness(hass, bulbs) == lit, (
        "the first sensor's Wait time ran out while the second's hadn't"
    )

    await let_time_pass(hass, frozen_time, 100)

    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}, (
        "the room stayed lit after every sensor's Wait time ran out"
    )


async def test_a_sensor_left_unavailable_does_not_keep_a_room_lit(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=tracking_scope)
    occupancy(hass, HALL_SENSOR, "off")
    occupancy(hass, SECOND_SENSOR, "unavailable")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR, SECOND_SENSOR], no_motion_wait=0)
    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()
    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}

    occupancy(hass, HALL_SENSOR, "off")
    await hass.async_block_till_done()
    await let_time_pass(hass, frozen_time, PAST_THE_WAIT)

    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}, (
        "an unavailable sensor held an empty room on"
    )


async def test_a_phase_change_repaints_a_lit_room(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """Evening becomes Night: the room follows, without anyone moving."""
    bulbs = await lit_room(hass, add_bulbs, setup_room, tracking_scope)

    await move_to_phase(hass, frozen_time, "Night")

    assert room_brightness(hass, bulbs) == {b.entity_id: NIGHT_BRIGHTNESS for b in bulbs}, (
        "the phase changed but the room did not follow"
    )


async def test_the_periodic_tick_keeps_a_lit_room_on_the_curve(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """The tick pulls an off-curve light back - unless it's tracked, in which
    case a change from outside reads as an override and is left alone."""
    bulbs = await lit_room(hass, add_bulbs, setup_room, tracking_scope)

    # Something else moves one fitting off the curve.
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": bulbs[0].entity_id, "brightness": 5},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert room_brightness(hass, bulbs)[bulbs[0].entity_id] == 5

    await let_time_pass(hass, frozen_time, 60)

    expected = {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    if tracking_scope is not None:
        expected[bulbs[0].entity_id] = 5  # protected, not overwritten
    assert room_brightness(hass, bulbs) == expected, (
        "the periodic tick did not do the right thing for this fitting"
    )


async def test_a_room_settles_to_its_idle_level_instead_of_going_dark(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """Idle Brightness redefines "off" for a room - the nightlight."""
    bulbs = await lit_room(
        hass, add_bulbs, setup_room, tracking_scope, no_motion_wait=0, evening_idle_brightness=25
    )

    occupancy(hass, HALL_SENSOR, "off")
    await hass.async_block_till_done()
    await let_time_pass(hass, frozen_time, PAST_THE_WAIT)

    assert room_brightness(hass, bulbs) == {b.entity_id: 25 for b in bulbs}, (
        "an empty room with an idle level should dim, not go dark"
    )


async def test_motion_brightens_a_room_sitting_at_its_idle_level(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """Everything's already on at the idle level, and must still brighten."""
    bulbs = await lit_room(
        hass, add_bulbs, setup_room, tracking_scope, no_motion_wait=0, evening_idle_brightness=25
    )
    occupancy(hass, HALL_SENSOR, "off")
    await hass.async_block_till_done()
    await let_time_pass(hass, frozen_time, PAST_THE_WAIT)
    assert room_brightness(hass, bulbs) == {b.entity_id: 25 for b in bulbs}

    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}, (
        "motion into an idle room did not bring it up to the curve"
    )


async def test_a_brightness_template_pins_one_fitting_to_its_own_level(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    """An absolute level; the rest of the room stays on the curve."""
    lamp = "light.hall_lamp"
    bulbs = await lit_room(
        hass,
        add_bulbs,
        setup_room,
        tracking_scope,
        brightness_template=f"{{{{ {{'{lamp}': 60}} }}}}",
    )

    expected = {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    expected[lamp] = 60
    assert room_brightness(hass, bulbs) == expected, (
        "the templated fitting should sit at its own level, the rest on the curve"
    )


async def test_a_phase_exclusion_turns_off_a_fitting_that_was_lit(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """Lit first, so the exclusion has to turn the spot off. (Can't tell
    needing_off from turn_on at brightness 0, which HA also turns off;
    that's for the unit tests.)"""
    spot = "light.hall_spot_1"
    bulbs = await lit_room(
        hass, add_bulbs, setup_room, tracking_scope, night_exclude_lights=[spot]
    )

    assert room_brightness(hass, bulbs)[spot] == CURVE_BRIGHTNESS, (
        "precondition: the spot must be lit before the exclusion applies"
    )

    await move_to_phase(hass, frozen_time, "Night")

    expected = {b.entity_id: NIGHT_BRIGHTNESS for b in bulbs}
    expected[spot] = "off"
    assert room_brightness(hass, bulbs) == expected, (
        "the excluded fitting should have been turned off, the rest left lit"
    )


async def test_a_light_switched_off_by_hand_stays_off(
    hass: HomeAssistant, add_bulbs, setup_room, tracked_scope, frozen_time
) -> None:
    """An off light is judged against its claims like an on one. The rest of
    the room stays on, so the scope isn't released."""
    bulbs = await lit_room(hass, add_bulbs, setup_room, tracked_scope)
    target = bulbs[0]

    await hass.services.async_call(
        "light", "turn_off", {"entity_id": target.entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(target.entity_id).state == "off", (
        "precondition: the hand turn-off must actually land, or this test proves nothing"
    )

    await let_time_pass(hass, frozen_time, 60)

    expected = {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    expected[target.entity_id] = "off"
    assert room_brightness(hass, bulbs) == expected, (
        "a light switched off by hand was relit by the next periodic tick"
    )
