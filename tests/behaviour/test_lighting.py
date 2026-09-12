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


async def test_it_turns_the_lights_on_when_a_room_becomes_occupied(
    hass: HomeAssistant, flare, add_bulbs, setup_room
) -> None:
    (bulb,) = await add_bulbs("hall")
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=[bulb], occupancy_sensors=[HALL_SENSOR])

    assert hass.states.get(bulb.entity_id).state == "off", (
        "the room should start dark, or this test proves nothing"
    )

    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()

    state = hass.states.get(bulb.entity_id)
    assert state.state == "on", "occupancy did not light the room"
    assert state.attributes["brightness"] == CURVE_BRIGHTNESS
