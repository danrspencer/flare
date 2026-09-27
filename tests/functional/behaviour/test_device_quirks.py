"""Bulbs that don't behave like the plain default: reporting colour in
another mode, differing RGB support, needing two writes, dropping off the
network. Each is a documented behaviour, proven through a real bulb."""

from homeassistant.core import HomeAssistant

from custom_components.flare.schedule.curve import kelvin_to_rgb
from tests.functional.behaviour.harness import (
    CURVE_BRIGHTNESS,
    CURVE_KELVIN,
    NIGHT_BRIGHTNESS,
    move_to_phase,
    occupancy,
)

SENSOR = "binary_sensor.device_quirks_occupancy"


async def test_a_bulb_reporting_colour_via_rgb_instead_of_kelvin_is_not_treated_as_overridden(
    hass: HomeAssistant, add_bulbs, setup_room, tracked_scope, frozen_time
) -> None:
    """An IKEA TRADFRI spot given Kelvin reports the equivalent RGB. It must
    not be read as overridden and excluded from updates."""
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

    # The device's own later report: the same colour under an unrelated
    # context, so only a value match can keep it. Brightness nudged by 1, or
    # the identical write wouldn't change the context.
    await bulb.async_echo(is_on=True, brightness=bulb.brightness - 1, rgb_color=bulb.rgb_color)
    await hass.async_block_till_done()

    await move_to_phase(hass, frozen_time, "Night")

    assert hass.states.get(bulb.entity_id).attributes.get("brightness") == NIGHT_BRIGHTNESS, (
        "a bulb that merely echoed its colour via rgb instead of kelvin, under an "
        "unrelated context, was wrongly excluded as if something else had taken it"
    )


async def test_an_rgb_capable_bulb_gets_colour_while_its_non_rgb_neighbour_stays_on_colour_temperature(
    hass: HomeAssistant, add_bulbs, setup_room, tracking_scope
) -> None:
    """One RGB-capable and one colour-temp bulb in the same room each get the
    attribute FLARE chose for them."""
    # Evening is a default "Prefer RGB During" phase.
    rgb_color = kelvin_to_rgb(CURVE_KELVIN)
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
    """A bulb matched by model gets two writes and ends up with both values.
    needs_two_step makes a combined call visibly fail."""
    (bulb,) = await add_bulbs(
        "tradfri_spot",
        area_id=tracking_scope,
        tradfri_spot={
            "device": {"manufacturer": "IKEA", "model": "TRADFRI bulb GU10 WS 400lm"},
            "needs_two_step": True,
        },
    )
    occupancy(hass, SENSOR, "off")
    # motion_on_transition: 0, so the step sleep is zero-length (safe under
    # the frozen clock).
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
    """A single bulb that drops out and returns already on, at a stale value,
    is brought back to the curve straight away by `recovered`. A single
    bulb, because a sibling staying reachable would stop `recovered`
    arming."""
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

    await bulb.async_echo(is_on=True, brightness=5, color_temp_kelvin=6500)
    await hass.async_block_till_done()

    assert hass.states.get(bulb.entity_id).attributes.get("brightness") == CURVE_BRIGHTNESS, (
        "a reconnected light reporting a stale value was left wrong instead of being "
        "corrected immediately, rather than waiting for the next scheduled tick"
    )
