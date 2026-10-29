"""Stored Traces: how many runs a room automation keeps traces of."""

from homeassistant.components.automation import DATA_COMPONENT

from tests.functional.blueprint.harness import light, setup_room_automation


def _stored_traces(hass, entity_id: str) -> int:
    return hass.data[DATA_COMPONENT].get_entity(entity_id)._trace_config["stored_traces"]


async def test_a_room_keeps_twenty_traces(hass):
    light(hass, "light.a", "on")
    await setup_room_automation(hass, room_target={"entity_id": "light.a"})

    assert _stored_traces(hass, "automation.room") == 20


async def test_a_room_keeps_as_many_as_it_is_set_to(hass):
    light(hass, "light.a", "on")
    await setup_room_automation(hass, room_target={"entity_id": "light.a"}, stored_traces=50)

    assert _stored_traces(hass, "automation.room") == 50
