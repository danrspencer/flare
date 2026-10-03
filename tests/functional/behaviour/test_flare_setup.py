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
)
from tests.functional.behaviour.harness import (
    CURVE_BRIGHTNESS,
    HALL_BULBS,
    HALL_SENSOR,
    add_flare,
    add_room_flares,
    flares_entry,
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


async def _finish(hass: HomeAssistant, result, name: str):
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": name})
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
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"lights_input": "room_target"}
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
    entry = await flares_entry(hass)

    result = await _start(hass, entry, "custom")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"automation": "automation.room"})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"lights_input": "room_target"}
    )
    result = await _finish(hass, result, "hall")

    assert result["errors"] == {"name": "already_configured"}


async def test_every_flare_shows_its_automation_and_where_its_lights_come_from(
    hass: HomeAssistant, add_bulbs, setup_room, zone
) -> None:
    """A room flare is edited like any other: its inputs are on show."""
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    await setup_room(lights=bulbs)
    await add_flare(hass, name="Hall")
    entry = await flares_entry(hass)
    (subentry_id,) = entry.subentries

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_FLARE), context={"source": "reconfigure", "subentry_id": subentry_id}
    )

    shown = {str(key): (key.description or {}).get("suggested_value") for key in result["data_schema"].schema}
    assert shown == {"name": "Hall", "lights_input": "room_target"}
    assert result["description_placeholders"] == {"automation": "room"}


async def test_a_flare_can_be_renamed(hass: HomeAssistant, add_bulbs, setup_room, zone) -> None:
    bulbs = await add_bulbs(*HALL_BULBS, area_id=zone)
    await setup_room(lights=bulbs)
    await add_flare(hass, name="Hall")
    (entry,) = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES]
    (subentry_id,) = entry.subentries

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_FLARE), context={"source": "reconfigure", "subentry_id": subentry_id}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Landing", "lights_input": "room_target"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    subentry = entry.subentries[subentry_id]
    assert (subentry.title, subentry.data["lights_input"]) == ("Landing", "room_target")


async def _two_rooms(hass: HomeAssistant, add_bulbs, zone) -> None:
    """Two room automations from the blueprint, each in an area of its own."""
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import entity_registry as er

    from tests.functional.behaviour.harness import ZONE, schedule_device, zone_device
    from tests.support import BLUEPRINT_PATH

    hall, landing = await add_bulbs("hall_a", "landing_a", area_id=zone)
    rooms = []
    for name, bulb in (("Hall", hall), ("Landing", landing)):
        inputs = {
            "schedule": schedule_device(hass),
            "zone": zone_device(hass, ZONE),
            "room_target": {"entity_id": [bulb.entity_id]},
        }
        rooms.append({"id": name.lower(), "alias": name, "use_blueprint": {"path": BLUEPRINT_PATH, "input": inputs}})
    assert await async_setup_component(hass, "automation", {"automation": rooms})
    await hass.async_block_till_done()
    for name in ("Hall", "Landing"):
        area = ar.async_get(hass).async_get_or_create(name).id
        er.async_get(hass).async_update_entity(f"automation.{name.lower()}", area_id=area)


async def test_every_room_can_be_given_a_flare_at_once(hass: HomeAssistant, add_bulbs, zone) -> None:
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    await _two_rooms(hass, add_bulbs, zone)

    result = await add_room_flares(hass)

    assert (result["reason"], result["description_placeholders"]) == ("flares_added", {"count": "2"})
    areas = {}
    for name in ("Hall", "Landing"):
        device_id = er.async_get(hass).async_get(f"light.{name.lower()}_flare").device_id
        areas[name] = ar.async_get(hass).async_get_area(dr.async_get(hass).async_get(device_id).area_id).name
    assert areas == {"Hall": "Hall", "Landing": "Landing"}


async def test_only_the_rooms_picked_get_a_flare(hass: HomeAssistant, add_bulbs, zone) -> None:
    await _two_rooms(hass, add_bulbs, zone)

    await add_room_flares(hass, ["automation.landing"])

    assert hass.states.get("light.landing_flare") is not None
    assert hass.states.get("light.hall_flare") is None


async def test_a_room_with_a_flare_is_not_offered_again(hass: HomeAssistant, add_bulbs, zone) -> None:
    await _two_rooms(hass, add_bulbs, zone)
    await add_room_flares(hass, ["automation.landing"])
    entry = await flares_entry(hass)

    result = await _start(hass, entry, "blueprint")
    offered = [o["value"] for o in result["data_schema"].schema["automation"].config["options"]]
    assert offered == ["automation.hall"]

    await add_room_flares(hass)
    result = await _start(hass, entry, "blueprint")
    assert result["reason"] == "every_room_has_a_flare"


async def test_adding_several_flares_reloads_the_entry_once(hass: HomeAssistant, add_bulbs, zone) -> None:
    from unittest.mock import patch

    await _two_rooms(hass, add_bulbs, zone)
    entry = await flares_entry(hass)
    reload = hass.config_entries.async_reload
    reloaded: list[str] = []

    async def counting(entry_id: str) -> bool:
        reloaded.append(entry_id)
        return await reload(entry_id)

    with patch.object(hass.config_entries, "async_reload", counting):
        await add_room_flares(hass)

    assert reloaded == [entry.entry_id]
    assert hass.states.get("light.hall_flare") and hass.states.get("light.landing_flare")


async def test_a_room_flare_is_the_same_however_it_was_added(hass: HomeAssistant, add_bulbs, zone) -> None:
    """The room list and "Another automation" differ only in how they ask."""
    await _two_rooms(hass, add_bulbs, zone)
    await add_room_flares(hass, ["automation.hall"])
    entry = await flares_entry(hass)
    result = await _start(hass, entry, "custom")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"automation": "automation.landing"})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"lights_input": "room_target"}
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Landing"})
    await hass.async_block_till_done()

    by_title = {s.title: dict(s.data) for s in entry.subentries.values()}
    hall, landing = by_title["Hall"], by_title["Landing"]
    assert set(hall) == set(landing)
    assert {k: v for k, v in hall.items() if k not in ("automation", "area_id")} == {
        k: v for k, v in landing.items() if k not in ("automation", "area_id")
    }
