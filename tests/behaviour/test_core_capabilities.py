"""
The things FLARE does in an ordinary room, on an ordinary day.

Basics only - each test is one capability a user would describe in a
sentence, asserted on the state real bulbs end up in. Edge cases and
feature interactions belong elsewhere; so do scenes, RGB, device
recovery and self-heal internals, which are features in their own right
rather than part of "does this light my hall".

Every assertion here reads the bulbs. Nothing checks which service was
called - tests/integration/test_blueprint.py already does that, and
doing it again here would forfeit the only thing this layer adds.
"""

from homeassistant.core import HomeAssistant

from tests.behaviour.conftest import (
    CURVE_BRIGHTNESS,
    let_time_pass,
    occupancy,
    room_brightness,
    set_phase,
)
from tests.behaviour.test_lighting import HALL_BULBS, HALL_SENSOR

# Long enough that the blueprint's own `now() - last_changed` check is
# satisfied for a room configured with no_motion_wait=0.
PAST_THE_WAIT = 120


async def lit_room(hass, add_bulbs, setup_room, **inputs):
    """An occupied room at the curve - the starting point for most of
    these, since "and then something changes" is the interesting half."""
    bulbs = await add_bulbs(*HALL_BULBS)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR], **inputs)
    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()
    return bulbs


async def test_it_turns_the_lights_off_once_the_room_is_empty(
    hass: HomeAssistant, flare, add_bulbs, setup_room, frozen_time
) -> None:
    bulbs = await lit_room(hass, add_bulbs, setup_room, no_motion_wait=0)
    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}

    occupancy(hass, HALL_SENSOR, "off")
    await hass.async_block_till_done()
    await let_time_pass(hass, frozen_time, PAST_THE_WAIT)

    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}, (
        "the room emptied but the lights stayed on"
    )


async def test_a_phase_change_repaints_a_lit_room(
    hass: HomeAssistant, flare, add_bulbs, setup_room
) -> None:
    """Evening becomes Night: the room follows, without anyone moving."""
    bulbs = await lit_room(hass, add_bulbs, setup_room)

    set_phase(hass, "Night", brightness=40, kelvin=2200)
    await hass.async_block_till_done()

    assert room_brightness(hass, bulbs) == {b.entity_id: 40 for b in bulbs}, (
        "the phase changed but the room did not follow"
    )


async def test_the_periodic_tick_keeps_a_lit_room_on_the_curve(
    hass: HomeAssistant, flare, add_bulbs, setup_room, frozen_time
) -> None:
    """The curve is flat in Morning and Night, so the sensor re-writes
    identical state and no state_changed fires. adaptive_tick exists to
    cover exactly that, and a light knocked off-curve by anything else
    is pulled back by it."""
    bulbs = await lit_room(hass, add_bulbs, setup_room)

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

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}, (
        "the periodic tick did not restore the room to the curve"
    )


async def test_a_room_settles_to_its_idle_level_instead_of_going_dark(
    hass: HomeAssistant, flare, add_bulbs, setup_room, frozen_time
) -> None:
    """Idle Brightness redefines "off" for a room - the nightlight."""
    bulbs = await lit_room(
        hass, add_bulbs, setup_room, no_motion_wait=0, evening_idle_brightness=25
    )

    occupancy(hass, HALL_SENSOR, "off")
    await hass.async_block_till_done()
    await let_time_pass(hass, frozen_time, PAST_THE_WAIT)

    assert room_brightness(hass, bulbs) == {b.entity_id: 25 for b in bulbs}, (
        "an empty room with an idle level should dim, not go dark"
    )


async def test_motion_brightens_a_room_sitting_at_its_idle_level(
    hass: HomeAssistant, flare, add_bulbs, setup_room, frozen_time
) -> None:
    """The other half of the nightlight, and the one that broke live:
    everything is already ON at the idle level, so "is anything off?"
    is the wrong question to ask about whether there is work to do."""
    bulbs = await lit_room(
        hass, add_bulbs, setup_room, no_motion_wait=0, evening_idle_brightness=25
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
    hass: HomeAssistant, flare, add_bulbs, setup_room
) -> None:
    """Absolute 0-255, not a multiplier of the curve - the rest of the
    room stays on the curve around it."""
    lamp = "light.hall_lamp"
    bulbs = await lit_room(
        hass,
        add_bulbs,
        setup_room,
        brightness_template=f"{{{{ {{'{lamp}': 60}} }}}}",
    )

    expected = {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    expected[lamp] = 60
    assert room_brightness(hass, bulbs) == expected, (
        "the templated fitting should sit at its own level, the rest on the curve"
    )


async def test_a_phase_exclusion_turns_one_fitting_off(
    hass: HomeAssistant, flare, add_bulbs, setup_room
) -> None:
    """Some fittings are wrong for some phases - a bright spot at
    night. Excluding one turns it off while the room stays lit."""
    spot = "light.hall_spot_1"
    bulbs = await lit_room(hass, add_bulbs, setup_room, evening_exclude_lights=[spot])

    expected = {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    expected[spot] = "off"
    assert room_brightness(hass, bulbs) == expected, (
        "the excluded fitting should be off and the rest of the room lit"
    )


# NOT covered here: a light switched off by hand staying off.
#
# It looks like a basic, and it is a real guarantee - classify() does
# not short-circuit on `not is_on`, so an off light with an `observed`
# claim that asked for brightness reads as `overridden` and is excluded.
# But none of that is reachable from this fixture. setup_room creates no
# FLARE Tracking state device, so the blueprint resolves
# tracking_scope_device_id to null and calls apply_lighting with
# tracking_device_id: null - which means "write, but track nothing". No
# claim is ever recorded, classify() sees no claims at all and returns
# "untracked", and every light stays fair game.
#
# Written as a test first, and it failed: the lamp came back on at the
# next tick. That is the harness having no scope, not the blueprint
# relighting an override - confirmed from the captured trace, which
# shows tracking_device_id = null on every apply_lighting call.
#
# Covering it needs setup_room to build a real state device in the
# room's area, the way tests/integration/test_blueprint.py's
# _register_tracking_scope does. Worth doing, but it is a fixture
# feature rather than one of the basics, so it is deliberately left out
# of this pass rather than left in as a test that cannot pass.
