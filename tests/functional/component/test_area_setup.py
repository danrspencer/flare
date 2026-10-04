"""Setting FLARE up, and then its areas: the integration page's main
button. Each area gets a zone, an automation from the blueprint in
automations.yaml, and a flare."""

from pathlib import Path

import yaml
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.blueprint_check import INSTALL_PATH
from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_ZONES,
)
from custom_components.flare.schedule.coordinator import schedule_instances
from custom_components.flare.zone.instance import zone_instances
from tests.support import BLUEPRINT_PATH


def _area(hass: HomeAssistant, name: str, *lights: str) -> str:
    area = ar.async_get(hass).async_get_or_create(name)
    for entity_id in lights:
        created = er.async_get(hass).async_get_or_create(
            "light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1]
        )
        er.async_get(hass).async_update_entity(created.entity_id, area_id=area.id)
        hass.states.async_set(entity_id, "off", {}, context=Context())
    return area.id


def _entry_of_type(hass: HomeAssistant, entry_type: str):
    return next(e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == entry_type)


def _automations(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text()) if path.exists() else []


def _device(hass: HomeAssistant, subentry_id: str) -> str:
    """The device of a schedule or zone subentry."""
    entry_id = next(e.entry_id for e in hass.config_entries.async_entries(DOMAIN) if subentry_id in e.subentries)
    return dr.async_get(hass).async_get_device_by_identifier((DOMAIN, subentry_id), entry_id).id


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


async def _submit(hass: HomeAssistant, result, user_input: dict):
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done()
    return result


async def _first_setup(hass: HomeAssistant, names: list[str]):
    """Through the schedule steps, to the areas form."""
    result = await _submit(hass, await _start(hass), {"count": len(names)})
    return await _submit(hass, result, {f"schedule_{n}": name for n, name in enumerate(names, 1)})


# --- First setup -------------------------------------------------------


async def test_first_setup_gives_every_area_with_lights_a_zone_automation_and_flare(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    kitchen = _area(hass, "Kitchen", "light.k")
    hall = _area(hass, "Hall", "light.h")
    _area(hass, "Garage")

    result = await _start(hass)
    assert result["step_id"] == "schedules"
    result = await _submit(hass, result, {"count": 1})
    assert result["step_id"] == "schedule_names"
    (name_field,) = result["data_schema"].schema
    assert name_field.description == {"suggested_value": "Home"}
    result = await _submit(hass, result, {"schedule_1": "Home"})
    assert result["step_id"] == "areas"
    assert sorted(result["data_schema"]({})["areas"]) == sorted([hall, kitchen]), "every area with lights, ticked"

    result = await _submit(hass, result, {"areas": [hall, kitchen]})

    assert result["reason"] == "setup_complete"
    assert result["description_placeholders"] == {
        "created": "a schedule called Home, 2 zones, 2 room automations and 2 flares"
    }
    zones = {z.title: z.subentry_id for z in zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES))}
    assert set(zones) == {"Hall", "Kitchen"}
    (schedule,) = schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))
    written = {a["alias"]: a for a in _automations(automations_file)}
    assert written["Kitchen Lighting"]["use_blueprint"] == {
        "path": INSTALL_PATH,
        "input": {
            "schedule": _device(hass, schedule.subentry_id),
            "zone": _device(hass, zones["Kitchen"]),
            "room_target": {"area_id": kitchen},
        },
    }
    assert hass.states.get("automation.kitchen_lighting") is not None
    assert er.async_get(hass).async_get("automation.kitchen_lighting").area_id == kitchen
    flares = _entry_of_type(hass, ENTRY_TYPE_FLARES)
    assert sorted(f.title for f in flares.subentries.values()) == ["Hall", "Kitchen"]


async def test_each_area_can_follow_its_own_schedule(stub_entry_setup, automations_file, hass: HomeAssistant):
    """With more than one schedule, each area picks one, or isn't set up."""
    _area(hass, "Kitchen", "light.k")
    _area(hass, "Bedroom", "light.b")
    _area(hass, "Loft", "light.l")

    result = await _first_setup(hass, ["Downstairs", "Upstairs"])
    defaults = result["data_schema"]({})
    assert defaults == {"set_up": "flare", "Bedroom": "schedule_1", "Kitchen": "schedule_1", "Loft": "schedule_1"}

    result = await _submit(hass, result, {"Bedroom": "schedule_2", "Kitchen": "schedule_1", "Loft": "skip"})

    assert result["description_placeholders"] == {
        "created": "schedules called Downstairs and Upstairs, 2 zones, 2 room automations and 2 flares"
    }
    schedules = {s.title: s.subentry_id for s in schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))}
    followed = {a["alias"]: a["use_blueprint"]["input"]["schedule"] for a in _automations(automations_file)}
    assert followed == {
        "Bedroom Lighting": _device(hass, schedules["Upstairs"]),
        "Kitchen Lighting": _device(hass, schedules["Downstairs"]),
    }


async def test_schedule_names_must_be_usable_and_distinct(stub_entry_setup, automations_file, hass: HomeAssistant):
    result = await _submit(hass, await _start(hass), {"count": 3})
    result = await _submit(hass, result, {"schedule_1": "Up stairs", "schedule_2": "up_stairs", "schedule_3": " !! "})

    assert result["errors"] == {"schedule_2": "duplicate_name", "schedule_1": "duplicate_name", "schedule_3": "invalid_name"}
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_a_house_with_no_lights_in_areas_still_gets_its_schedule(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    result = await _first_setup(hass, ["Home"])

    assert result["reason"] == "setup_complete"
    assert result["description_placeholders"] == {"created": "a schedule called Home"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 3
    assert zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES)) == []


# --- Set up area, once FLARE exists --------------------------------------


async def _set_up_flare(hass: HomeAssistant, areas: list[str]) -> None:
    result = await _first_setup(hass, ["Home"])
    if result["type"] == "form":
        await _submit(hass, result, {"areas": areas})


async def test_set_up_area_offers_only_areas_without_a_flare_automation(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    kitchen = _area(hass, "Kitchen", "light.k")
    await _set_up_flare(hass, [kitchen])
    hall = _area(hass, "Hall", "light.h")

    result = await _start(hass)
    assert result["step_id"] == "areas"
    assert result["data_schema"]({}) == {"set_up": "flare", "areas": []}, "nothing ticked once FLARE is set up"
    offered = [o["value"] for o in result["data_schema"].schema["areas"].config["options"]]
    assert offered == [hall]

    result = await _submit(hass, result, {"areas": [hall]})

    assert result["reason"] == "areas_set_up"
    assert result["description_placeholders"] == {"created": "1 zone, 1 room automation and 1 flare"}
    assert sorted(a["alias"] for a in _automations(automations_file)) == ["Hall Lighting", "Kitchen Lighting"]


async def test_set_up_area_with_every_area_done_says_so(stub_entry_setup, automations_file, hass: HomeAssistant):
    kitchen = _area(hass, "Kitchen", "light.k")
    await _set_up_flare(hass, [kitchen])

    result = await _start(hass)

    assert result["reason"] == "every_area_set_up"


async def test_an_existing_zone_with_the_areas_name_is_reused(stub_entry_setup, automations_file, hass: HomeAssistant):
    await _set_up_flare(hass, [])
    zones = _entry_of_type(hass, ENTRY_TYPE_ZONES)
    result = await hass.config_entries.subentries.async_init((zones.entry_id, "state"), context={"source": "user"})
    await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Kitchen"})
    await hass.async_block_till_done()
    (zone,) = zone_instances(zones)
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, await _start(hass), {"areas": [kitchen]})

    assert result["description_placeholders"] == {"created": "1 room automation and 1 flare"}
    assert [z.subentry_id for z in zone_instances(zones)] == [zone.subentry_id]
    (written,) = _automations(automations_file)
    assert written["use_blueprint"]["input"]["zone"] == _device(hass, zone.subentry_id)


async def test_an_area_can_get_just_a_zone(stub_entry_setup, automations_file, hass: HomeAssistant):
    """And it's offered again, so it can get the rest later."""
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, await _first_setup(hass, ["Home"]), {"set_up": "zone", "areas": [kitchen]})

    assert result["description_placeholders"] == {"created": "a schedule called Home and 1 zone"}
    assert [z.title for z in zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES))] == ["Kitchen"]
    assert _automations(automations_file) == []
    result = await _start(hass)
    assert [o["value"] for o in result["data_schema"].schema["areas"].config["options"]] == [kitchen]


async def test_an_area_can_get_a_zone_and_automation_without_a_flare(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, await _first_setup(hass, ["Home"]), {"set_up": "automation", "areas": [kitchen]})

    assert result["description_placeholders"] == {"created": "a schedule called Home, 1 zone and 1 room automation"}
    assert hass.states.get("automation.kitchen_lighting") is not None
    assert _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries == {}


# --- automations.yaml ----------------------------------------------------


async def test_the_users_own_automations_are_kept(stub_entry_setup, automations_file, hass: HomeAssistant):
    mine = {"id": "mine", "alias": "Mine", "triggers": [], "actions": []}
    automations_file.write_text(yaml.safe_dump([mine]))
    kitchen = _area(hass, "Kitchen", "light.k")

    await _submit(hass, await _first_setup(hass, ["Home"]), {"areas": [kitchen]})

    assert [a["alias"] for a in _automations(automations_file)] == ["Mine", "Kitchen Lighting"]


async def test_without_automations_yaml_loaded_nothing_is_written(stub_entry_setup, hass: HomeAssistant):
    """configuration.yaml not including automations.yaml: the file is put
    back exactly as it was, comments and all."""
    from homeassistant.setup import async_setup_component

    Path(hass.config.config_dir, "configuration.yaml").write_text("default_config_not_here: {}\n")
    assert await async_setup_component(hass, "automation", {})
    automations = Path(hass.config.config_dir, "automations.yaml")
    original = "# kept by hand\n[]\n"
    automations.write_text(original)
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, await _first_setup(hass, ["Home"]), {"areas": [kitchen]})

    assert result["reason"] == "automations_not_loaded"
    assert automations.read_text() == original
    assert _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries == {}


async def test_the_blueprint_is_installed_if_it_isnt_there(stub_entry_setup, automations_file, hass: HomeAssistant):
    installed = Path(hass.config.config_dir, "blueprints", "automation", BLUEPRINT_PATH)
    installed.unlink()
    from homeassistant.components.automation.helpers import async_get_blueprints

    await async_get_blueprints(hass).async_reset_cache()
    kitchen = _area(hass, "Kitchen", "light.k")

    await _submit(hass, await _first_setup(hass, ["Home"]), {"areas": [kitchen]})

    assert installed.exists()
    assert hass.states.get("automation.kitchen_lighting") is not None


async def test_an_entry_deleted_by_hand_is_created_again(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Only the missing one, and areas are offered as on first setup."""
    await _set_up_flare(hass, [])
    flares = _entry_of_type(hass, ENTRY_TYPE_FLARES)
    await hass.config_entries.async_remove(flares.entry_id)
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _start(hass)
    assert result["data_schema"]({})["areas"] == [kitchen]
    await _submit(hass, result, {"areas": [kitchen]})

    assert len(hass.config_entries.async_entries(DOMAIN)) == 3
    assert [f.title for f in _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries.values()] == ["Kitchen"]


async def test_set_up_area_needs_a_schedule(stub_entry_setup, hass: HomeAssistant):
    for entry_type in (ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_ZONES, ENTRY_TYPE_FLARES):
        MockConfigEntry(
            domain=DOMAIN, data={CONF_ENTRY_TYPE: entry_type}, unique_id=f"{DOMAIN}_{entry_type}", version=3
        ).add_to_hass(hass)

    result = await _start(hass)

    assert result["reason"] == "no_schedules"
