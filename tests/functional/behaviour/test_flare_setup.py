"""Adding a flare over an automation that isn't picked from the FLARE
blueprint list, and editing one."""

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    SUBENTRY_TYPE_FLARE,
    TURN_OFF_FLARE,
    TURN_OFF_LIGHT,
)
from tests.functional.behaviour.harness import (
    CURVE_BRIGHTNESS,
    HALL_BULBS,
    HALL_SENSOR,
    add_flare,
    occupancy,
    room_brightness,
)


async def _flares_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_FLARES}, unique_id=f"{DOMAIN}_{ENTRY_TYPE_FLARES}", version=3
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _start(hass: HomeAssistant, entry, path: str):
    flows = hass.config_entries.subentries
    result = await flows.async_init((entry.entry_id, SUBENTRY_TYPE_FLARE), context={"source": "user"})
    return await flows.async_configure(result["flow_id"], {"next_step_id": path})


async def _finish(hass: HomeAssistant, result, name: str, turn_off: str = TURN_OFF_FLARE):
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": name, "turn_off": turn_off})
    await hass.async_block_till_done()
    return result


async def _bare_on(hass: HomeAssistant, flare: str) -> None:
    await hass.services.async_call("light", "turn_on", {"entity_id": flare}, blocking=True)
    await hass.async_block_till_done()


async def test_any_blueprints_automation_can_be_a_flare_by_naming_its_inputs(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    occupancy(hass, HALL_SENSOR, "off")
    await setup_room(lights=bulbs, occupancy_sensors=[HALL_SENSOR])
    entry = await _flares_entry(hass)

    result = await _start(hass, entry, "custom")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"automation": "automation.room"})
    assert result["step_id"] == "custom_inputs"
    offered = {str(key): value.config.get("options") for key, value in result["data_schema"].schema.items()}
    assert offered["lights_input"] == [
        "day_exclude_lights",
        "evening_exclude_lights",
        "morning_exclude_lights",
        "night_exclude_lights",
        "room_target",
    ]
    assert offered["zone_input"] == ["zone"]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"lights_input": "room_target", "zone_input": "zone"}
    )
    result = await _finish(hass, result, "Hall")
    assert result["type"] == "create_entry"

    await _bare_on(hass, "light.hall_flare")

    assert room_brightness(hass, bulbs) == {b.entity_id: CURVE_BRIGHTNESS for b in bulbs}


async def test_an_input_the_automation_never_set_is_refused(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    await setup_room(lights=bulbs)
    entry = await _flares_entry(hass)

    result = await _start(hass, entry, "custom")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"automation": "automation.room"})
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"lights_input": "day_exclude_lights"})

    assert result["errors"] == {"lights_input": "input_not_set"}


async def test_a_plain_automation_is_a_flare_over_the_lights_picked_for_it(hass: HomeAssistant, add_bulbs) -> None:
    bulbs = await add_bulbs("porch_1", "porch_2")
    entity_ids = [b.entity_id for b in bulbs]
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "id": "porch",
                    "alias": "porch",
                    "triggers": [],
                    "actions": [{"action": "light.turn_on", "target": {"entity_id": entity_ids}, "data": {"brightness": 99}}],
                }
            ]
        },
    )
    await hass.async_block_till_done()
    entry = await _flares_entry(hass)

    result = await _start(hass, entry, "custom")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"automation": "automation.porch"})
    assert result["step_id"] == "custom_target"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"lights_target": {"entity_id": entity_ids}}
    )
    result = await _finish(hass, result, "Porch")
    assert result["type"] == "create_entry"
    assert sorted(hass.states.get("light.porch_flare").attributes["entity_id"]) == sorted(entity_ids)

    await _bare_on(hass, "light.porch_flare")

    assert room_brightness(hass, bulbs) == {e: 99 for e in entity_ids}


async def test_with_no_room_automation_the_blueprint_list_says_so(hass: HomeAssistant) -> None:
    entry = await _flares_entry(hass)

    result = await _start(hass, entry, "blueprint")

    assert result["type"] == "abort" and result["reason"] == "no_room_automations"


async def test_a_flare_name_already_in_use_is_refused(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    await setup_room(lights=bulbs)
    await add_flare(hass, name="Hall")
    (entry,) = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES]

    result = await _start(hass, entry, "blueprint")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"automation": "automation.room"})
    result = await _finish(hass, result, "hall")

    assert result["errors"] == {"name": "already_configured"}


async def test_a_flare_can_be_renamed_and_its_turn_off_changed(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    await setup_room(lights=bulbs)
    await add_flare(hass, name="Hall")
    (entry,) = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES]
    (subentry_id,) = entry.subentries

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_FLARE), context={"source": "reconfigure", "subentry_id": subentry_id}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Landing", "turn_off": TURN_OFF_LIGHT}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    subentry = entry.subentries[subentry_id]
    assert (subentry.title, subentry.data["turn_off"], subentry.data["lights_input"]) == ("Landing", TURN_OFF_LIGHT, "room_target")
