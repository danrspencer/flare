"""
Real bulbs that don't play along the way the curve expects: one that
reports its colour back in a mode nobody asked for, two that differ in
what they support, one that needs two separate writes, one that drops
off the network and comes back. Split out of test_core_capabilities.py/
test_lighting.py because every test here needs a FakeBulb variant that
isn't the plain colour-temp-only default - see conftest.py's own
FakeBulb docstring for why those variants live there and not here.

Each test pins a behaviour documented in docs/blueprint.md or
docs/advanced/reference.md that, before this file, only
test_override_protection.py/test_grouping.py had proven at the pure
value/mocked-call level - never through a real bulb and real dispatch,
which is the one thing this layer exists to add (see conftest.py's own
module docstring). That gap is exactly where this session's two release
bugs lived: grouping.py and override_protection.py were each correct in
isolation and wrong once a real device's actual reporting quirks met
them.
"""

from homeassistant.core import HomeAssistant

from tests.behaviour.conftest import (
    CURVE_BRIGHTNESS,
    CURVE_KELVIN,
    SCHEDULE_SENSOR,
    occupancy,
    set_phase,
)

SENSOR = "binary_sensor.device_quirks_occupancy"


async def test_a_bulb_reporting_colour_via_rgb_instead_of_kelvin_is_not_treated_as_overridden(
    hass: HomeAssistant, add_bulbs, setup_room, tracked_scope
) -> None:
    """The live incident this session's release fixed: an IKEA TRADFRI
    spot given a Kelvin claim settled at (and only ever reports) the
    equivalent RGB colour - a real device quirk, not a dropped write or
    a genuine override. test_override_protection.py already proves the
    value-level comparison; this proves a real bulb that does this
    isn't excluded from every future update - the actual, observable
    cost of being wrongly classified `overridden` (CLAUDE.md's "Known
    limitation" under Override protection).

    Needs tracked_scope specifically: there is no meaningful untracked
    half of "does this get excluded as overridden" - untracked, nothing
    holds a claim to exclude it from in the first place.
    """
    (bulb,) = await add_bulbs("spot", area_id=tracked_scope, spot={"reports_via_rgb": True})
    occupancy(hass, SENSOR, "off")
    await setup_room(lights=[bulb], occupancy_sensors=[SENSOR])

    occupancy(hass, SENSOR, "on")
    await hass.async_block_till_done()

    state = hass.states.get(bulb.entity_id)
    assert state.attributes.get("color_temp_kelvin") is None, (
        "precondition: the bulb must actually echo via rgb_color, not color_temp_kelvin, "
        "or this test can't tell a real fix from a no-op"
    )
    assert state.attributes.get("rgb_color") is not None

    # The device re-publishes its own state independently sometime
    # later - a retained MQTT message, a Zigbee heartbeat - essentially
    # the same colour, but under a context unrelated to FLARE's own
    # write (what actually happened live was recovery from an ~89
    # minute unavailable spell; what matters here is only that the
    # context match this claim relied on is now gone, forcing
    # classify() to fall back to comparing values). brightness is
    # nudged by 1 (still well within tolerance) rather than repeated
    # byte-for-byte: two consecutive hass.states.async_set calls with
    # identical values collapse into one state_reported event and the
    # second call's context is silently discarded (see CLAUDE.md's
    # Testing section) - which would leave the ORIGINAL context in
    # place and prove nothing.
    await bulb.async_echo(is_on=True, brightness=bulb.brightness - 1, rgb_color=bulb.rgb_color)
    await hass.async_block_till_done()

    set_phase(hass, "Day", brightness=40, kelvin=2200)
    await hass.async_block_till_done()

    assert hass.states.get(bulb.entity_id).attributes.get("brightness") == 40, (
        "a bulb that merely echoed its colour via rgb instead of kelvin, under an "
        "unrelated context, was wrongly excluded as if something else had taken it"
    )


async def test_an_rgb_capable_bulb_gets_colour_while_its_non_rgb_neighbour_stays_on_colour_temperature(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    """'Prefer RGB During' auto-detects support per light
    (docs/blueprint.md: "Lights without RGB are unaffected"). test_grouping.py
    already proves the pure routing decision, and test_blueprint.py
    proves the right flag reaches apply_lighting - neither proves two
    real bulbs in the SAME room, one RGB-capable and one not, each
    actually land on the attribute FLARE decided for them.
    """
    rgb_color = (255, 147, 41)
    hass.states.async_set(
        SCHEDULE_SENSOR,
        "Evening",  # a default "Prefer RGB During" phase
        {"brightness": CURVE_BRIGHTNESS, "color_temp": CURVE_KELVIN, "rgb_color": list(rgb_color)},
    )
    rgb_bulb, ct_bulb = await add_bulbs(
        "rgb_spot", "ct_spot", area_id=tracking_scope, rgb_spot={"supports_rgb": True}
    )
    occupancy(hass, SENSOR, "off")
    await setup_room(lights=[rgb_bulb, ct_bulb], occupancy_sensors=[SENSOR])

    occupancy(hass, SENSOR, "on")
    await hass.async_block_till_done()

    rgb_state = hass.states.get(rgb_bulb.entity_id)
    ct_state = hass.states.get(ct_bulb.entity_id)
    assert rgb_state.attributes.get("rgb_color") == rgb_color, (
        "the RGB-capable bulb should have received the sensor's rgb_color"
    )
    assert ct_state.attributes.get("color_temp_kelvin") == CURVE_KELVIN, (
        "the non-RGB bulb should be unaffected by Prefer RGB During and stay on colour temperature"
    )
    assert ct_state.attributes.get("color_mode") == "color_temp", (
        "a bulb with no RGB support should never be sent an rgb_color command - note HA's own "
        "LightEntity backfills a derived rgb_color attribute for display on ANY colour-temp light "
        "regardless of support, so color_mode is the only reliable signal of which command it got"
    )


async def test_a_device_matching_the_two_step_pattern_lands_at_the_right_brightness_and_colour(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    """Two-step transitions send brightness and colour as two separate
    light.turn_on calls, for bulbs that snap or drop one of the two when
    combined - picked up by device manufacturer/model, no label needed
    (docs/advanced/reference.md's "Two-step transition bulbs").
    test_grouping.py/test_services.py already prove the call SHAPE (two
    calls, the right data in each); nothing before this proved a real
    bulb's own final state reflects BOTH writes. needs_two_step models
    the actual defect (brightness+colour together only apply one of the
    two) - without it, a single combined call would land at the exact
    same final values as two separate ones and this test couldn't tell
    a working automatic routing decision from a broken one.
    """
    (bulb,) = await add_bulbs(
        "tradfri_spot",
        area_id=tracking_scope,
        tradfri_spot={
            "device": {"manufacturer": "IKEA", "model": "TRADFRI bulb GU10 WS 400lm"},
            "needs_two_step": True,
        },
    )
    occupancy(hass, SENSOR, "off")
    # motion_on_transition: 0, so the two-step call's real
    # asyncio.sleep(half_transition) is a zero-length one - safe under
    # this directory's frozen_time (see CLAUDE.md: a zero sleep is
    # routed via call_soon, a nonzero one under a frozen clock is not).
    await setup_room(lights=[bulb], occupancy_sensors=[SENSOR], motion_on_transition=0)

    occupancy(hass, SENSOR, "on")
    await hass.async_block_till_done()

    state = hass.states.get(bulb.entity_id)
    assert state.state == "on"
    assert state.attributes.get("brightness") == CURVE_BRIGHTNESS, (
        "the brightness-only first call should have landed"
    )
    assert state.attributes.get("color_temp_kelvin") == CURVE_KELVIN, (
        "the colour-carrying second call should have landed on top of it, not replaced it"
    )


async def test_a_light_that_reconnects_already_on_is_corrected_immediately_not_on_the_next_scheduled_tick(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    """docs/blueprint.md: "Lights that come back online... the room
    updates straight away rather than waiting for the next scheduled
    update." That's the `recovered` trigger - test_blueprint.py proves
    the SERVICE gets called when it fires; this proves a real bulb that
    actually drops out and reconnects lands back on the curve without
    needing update_interval to pass.

    A bulb that keeps its last state across a mains dropout (many do)
    comes back on at whatever it last held, not the curve's current
    value. This is the one case `recovered` can actually relight
    anything by itself: `allow_turn_on`'s `occupied` gate reads
    resolved_entities' own live state, so a room with no light left on
    is never "occupied" no matter how many bulbs return - see "When
    lights turn on and off" in docs/blueprint.md ("a bulb that
    reconnects after a power cut stays off if the rest of the room is
    dark"). A bulb reappearing already ON is what flips that gate open,
    which is why this uses a single-bulb room rather than a sibling
    that stayed reachable throughout (CLAUDE.md's own "one flaky bulb
    recovering beside healthy siblings doesn't fire this" - a second,
    still-reachable bulb would stop the aggregate ever dipping to
    false, so `recovered` would never arm at all).
    """
    (bulb,) = await add_bulbs("recovering", area_id=tracking_scope)
    occupancy(hass, SENSOR, "off")
    await setup_room(lights=[bulb], occupancy_sensors=[SENSOR])
    occupancy(hass, SENSOR, "on")
    await hass.async_block_till_done()
    assert hass.states.get(bulb.entity_id).attributes.get("brightness") == CURVE_BRIGHTNESS, (
        "precondition: the room must be lit before the drop-out, or recovery proves nothing"
    )

    await bulb.async_go_unavailable()
    await hass.async_block_till_done()
    assert hass.states.get(bulb.entity_id).state == "unavailable"

    # It reconnects already on, at some stale value from before the
    # drop-out - not because FLARE asked for anything.
    await bulb.async_echo(is_on=True, brightness=5, color_temp_kelvin=6500)
    await hass.async_block_till_done()

    assert hass.states.get(bulb.entity_id).attributes.get("brightness") == CURVE_BRIGHTNESS, (
        "a reconnected light reporting a stale value was left wrong instead of being "
        "corrected immediately, rather than waiting for the next scheduled tick"
    )
