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


async def lit_room(hass, add_bulbs, setup_room, tracking_scope, **inputs):
    """An occupied room at the curve - the starting point for most of
    these, since "and then something changes" is the interesting half.

    tracking_scope is the (parametrized) area id from conftest.py - see
    that fixture for why every test below runs twice, once with the
    room's lights untracked and once with a real FLARE Tracking scope
    claiming them.
    """
    bulbs = await add_bulbs(*HALL_BULBS, area_id=tracking_scope)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR], **inputs)
    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()
    return bulbs


async def test_the_room_ends_up_dark_once_it_is_empty(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """Outcome, not mechanism, and deliberately so.

    Two branches can satisfy this - the motion_off turn-off, and
    self-heal retrying it on the next tick. Mutation testing showed as
    much: breaking `turn_off_entities` so motion_off switches nothing
    off still leaves the room dark, because self-heal gets there. That
    is the right answer for a behaviour test (an empty room going dark
    is the promise; which branch delivered it is not), but the name has
    to say so, because it does NOT pin motion_off specifically.
    """
    bulbs = await lit_room(hass, add_bulbs, setup_room, tracking_scope, no_motion_wait=0)
    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}

    occupancy(hass, HALL_SENSOR, "off")
    await hass.async_block_till_done()
    await let_time_pass(hass, frozen_time, PAST_THE_WAIT)

    assert room_brightness(hass, bulbs) == {b.entity_id: "off" for b in bulbs}, (
        "the room emptied but the lights stayed on"
    )


async def test_a_phase_change_repaints_a_lit_room(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    """Evening becomes Night: the room follows, without anyone moving."""
    bulbs = await lit_room(hass, add_bulbs, setup_room, tracking_scope)

    set_phase(hass, "Night", brightness=40, kelvin=2200)
    await hass.async_block_till_done()

    assert room_brightness(hass, bulbs) == {b.entity_id: 40 for b in bulbs}, (
        "the phase changed but the room did not follow"
    )


async def test_the_periodic_tick_keeps_a_lit_room_on_the_curve(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope, frozen_time
) -> None:
    """The curve is flat in Morning and Night, so the sensor re-writes
    identical state and no state_changed fires. The periodic tick
    exists to cover exactly that, and a light knocked off-curve by
    anything else is pulled back by it - UNLESS "anything else" is
    exactly what override protection exists to recognise.

    Tracked and untracked genuinely diverge here, and both are correct.
    `light.turn_on` from outside flare is indistinguishable from a
    person reaching for the switch - untracked, there is no claim to
    protect it, so the tick pulls it straight back; tracked, the room's
    real Tracking scope classifies it as overridden (see CLAUDE.md's
    Override protection) and the tick leaves that one fitting alone
    while still correcting every other. Caught by tracking_scope
    actually wiring a real scope: this assertion originally expected a
    full restore in both cases, and only the untracked half is that.
    """
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
    """The other half of the nightlight, and the one that broke live:
    everything is already ON at the idle level, so "is anything off?"
    is the wrong question to ask about whether there is work to do."""
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
    """Absolute 0-255, not a multiplier of the curve - the rest of the
    room stays on the curve around it."""
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
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    """Some fittings are wrong for some phases - a bright spot at night.

    The room is lit WITHOUT the exclusion first, so the spot is
    genuinely on before the excluding phase arrives. Otherwise this only
    proves an excluded fitting is never switched ON, and no turn-off
    ever runs - which is what the first version of this test did.

    Known limit, and not fixable from this layer: it pins the OUTCOME,
    not which mechanism delivers it. Disabling grouping.py's
    `if brightness <= 0` branch still passes, because the fitting then
    falls into group.combined and gets light.turn_on at brightness 0 -
    and HA's light component redirects exactly that to async_turn_off
    (components/light/__init__.py: "If brightness is set to 0, this
    service will turn the light off"). Both routes end with the bulb
    off, so no assertion on bulb state can tell them apart. Pinning
    `needing_off` specifically belongs in tests/test_grouping.py, which
    can see the groups themselves.
    """
    spot = "light.hall_spot_1"
    bulbs = await lit_room(
        hass, add_bulbs, setup_room, tracking_scope, night_exclude_lights=[spot]
    )

    assert room_brightness(hass, bulbs)[spot] == CURVE_BRIGHTNESS, (
        "precondition: the spot must be lit before the exclusion applies"
    )

    set_phase(hass, "Night", brightness=CURVE_BRIGHTNESS, kelvin=2200)
    await hass.async_block_till_done()

    expected = {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}
    expected[spot] = "off"
    assert room_brightness(hass, bulbs) == expected, (
        "the excluded fitting should have been turned off, the rest left lit"
    )


# STILL NOT covered here: a light switched off by hand staying off.
#
# It looks like a basic, and it is a real guarantee - classify() does
# not short-circuit on `not is_on`, so an off light with an `observed`
# claim that asked for brightness reads as `overridden` and is excluded.
#
# The original reason this was out of reach is gone: conftest.py's
# tracking_scope/tracked_scope fixtures now build a real FLARE Tracking
# state device and assign every bulb its area, exactly what was missing
# below. What's still missing is the test itself - depend on
# tracked_scope (not tracking_scope; there is no meaningful untracked
# half of "does an override stick"), turn a bulb off by hand, and assert
# it stays off through the next tick. Left out of this pass
# because writing and mutation-verifying it is its own piece of work,
# not because it can't be done.
