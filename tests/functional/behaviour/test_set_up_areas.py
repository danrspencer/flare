"""An area set up from the integration page works with nothing else done:
its automation drives the room, and its flare switches it."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.flare.const import DOMAIN
from tests.functional.behaviour.harness import (
    CURVE_BRIGHTNESS,
    HALL_BULBS,
    HALL_SENSOR,
    occupancy,
    room_brightness,
)


async def _set_up_hall(hass: HomeAssistant, add_bulbs):
    """The Hall's bulbs and occupancy sensor, then the main flow picking it."""
    hall = ar.async_get(hass).async_get_or_create("Hall").id
    bulbs = await add_bulbs(*HALL_BULBS, area_id=hall)
    sensor = er.async_get(hass).async_get_or_create(
        "binary_sensor", "test", "hall_occupancy", suggested_object_id=HALL_SENSOR.split(".", 1)[1]
    )
    er.async_get(hass).async_update_entity(sensor.entity_id, area_id=hall)
    occupancy(hass, HALL_SENSOR, "off")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "areas"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"areas": {}})
    await hass.async_block_till_done()
    assert result["reason"] == "setup_complete", result
    return bulbs


async def test_motion_lights_a_set_up_area_at_the_curve(hass: HomeAssistant, add_bulbs, automations_file) -> None:
    bulbs = await _set_up_hall(hass, add_bulbs)
    assert set(room_brightness(hass, bulbs).values()) == {"off"}

    occupancy(hass, HALL_SENSOR, "on")
    await hass.async_block_till_done()

    assert set(room_brightness(hass, bulbs).values()) == {CURVE_BRIGHTNESS}


async def test_a_set_up_areas_flare_turns_the_room_on_at_the_curve(
    hass: HomeAssistant, add_bulbs, automations_file
) -> None:
    bulbs = await _set_up_hall(hass, add_bulbs)

    await hass.services.async_call("light", "turn_on", {"entity_id": "light.hall_flare"}, blocking=True)
    await hass.async_block_till_done()

    assert set(room_brightness(hass, bulbs).values()) == {CURVE_BRIGHTNESS}
