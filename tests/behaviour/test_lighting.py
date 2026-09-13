"""
What FLARE does when someone walks into a room.

Each test is named for the capability it pins, and asserts on the state
a real bulb actually ends up in - not on which services were called
with what. See conftest.py for why that distinction is the entire
reason this layer exists.
"""

from homeassistant.core import HomeAssistant

from tests.behaviour.conftest import CURVE_BRIGHTNESS, occupancy

HALL_SENSOR = "binary_sensor.hall_occupancy"

# A real room is several fittings, not one bulb, and the difference is
# not cosmetic: with a single light, grouping.py's _bucket_by_multiplier
# always produces exactly one bucket holding one entity, so the whole
# bucketing path goes unexercised. Six on one curve is one bucket of
# six - the shape an actual room produces.
HALL_BULBS = (
    "hall_pendant",
    "hall_spot_1",
    "hall_spot_2",
    "hall_spot_3",
    "hall_spot_4",
    "hall_lamp",
)


def brightness_of(hass: HomeAssistant, bulbs) -> dict[str, object]:
    """Every bulb's state as {entity_id: brightness or 'off'}.

    Asserting on the whole room at once means a failure names which
    fittings were wrong rather than stopping at the first, which is the
    difference between "the room didn't light" and "two spots missed it".
    """
    result: dict[str, object] = {}
    for bulb in bulbs:
        state = hass.states.get(bulb.entity_id)
        result[bulb.entity_id] = (
            state.attributes.get("brightness") if state.state == "on" else "off"
        )
    return result


async def test_it_turns_the_lights_on_when_a_room_becomes_occupied(
    hass: HomeAssistant, flare, add_bulbs, setup_room
) -> None:
    bulbs = await add_bulbs(*HALL_BULBS)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR])

    assert brightness_of(hass, bulbs) == {bulb.entity_id: "off" for bulb in bulbs}, (
        "the room should start dark, or this test proves nothing"
    )

    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()

    assert brightness_of(hass, bulbs) == {
        bulb.entity_id: CURVE_BRIGHTNESS for bulb in bulbs
    }, "occupancy did not light the whole room to the curve"
