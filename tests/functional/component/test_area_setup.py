"""Setting FLARE up, and then its areas: the integration page's main
button. Each area gets a zone, an automation from the blueprint in
automations.yaml, and a flare."""

from pathlib import Path

import pytest
import yaml
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
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


def _area(hass: HomeAssistant, name: str, *lights: str, floor: str | None = None) -> str:
    area = ar.async_get(hass).async_get_or_create(name)
    if floor is not None:
        floors = fr.async_get(hass)
        floor_id = (floors.async_get_floor_by_name(floor) or floors.async_create(floor)).floor_id
        ar.async_get(hass).async_update(area.id, floor_id=floor_id)
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


def _area_fields(result) -> dict:
    """The Areas section's fields, by name."""
    (key,) = [k for k in result["data_schema"].schema if str(k) == "areas"]
    return {str(k): v for k, v in result["data_schema"].schema[key].schema.schema.items()}


def _defaults(result) -> dict:
    """The form's starting values, the Areas section's flattened in."""
    defaults = result["data_schema"]({"areas": {}})
    return {"set_up": defaults["set_up"], **defaults["areas"]}


def _choose(hass: HomeAssistant, result, area_ids: list[str], **extra) -> dict:
    """The areas form's input: each area in `area_ids` on the one schedule,
    every other area Don't set up."""
    names = {ar.async_get(hass).async_get_area(a).name for a in area_ids}
    fields = _area_fields(result)
    (schedule,) = {o["value"] for o in _options(result, next(iter(fields)))} - {"skip"} if fields else {None}
    return {"areas": {f: schedule if f in names else "skip" for f in fields}, **extra}


def _options(result, field: str) -> list[dict]:
    return _area_fields(result)[field].config["options"]


def _picked(hass: HomeAssistant, result) -> list[str]:
    """The areas that start set up."""
    names = {a.name: a.id for a in ar.async_get(hass).async_list_areas()}
    return sorted(names[f] for f, v in _defaults(result).items() if f != "set_up" and v != "skip")


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
    assert _picked(hass, result) == sorted([hall, kitchen]), "every area with lights starts set up"

    result = await _submit(hass, result, _choose(hass, result, [hall, kitchen]))

    assert result["reason"] == "setup_complete"
    assert result["description_placeholders"] == {
        "schedules": "Home", "zones": "2", "automations": "2", "flares": "2"
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


async def test_its_automations_carry_a_flare_label(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Created once, and reused by a later run."""
    from homeassistant.helpers import label_registry as lr

    kitchen = _area(hass, "Kitchen", "light.k")
    hall = _area(hass, "Hall", "light.h")
    await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen]))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await _submit(hass, result, _choose(hass, result, [hall], set_up="automation"))

    (label,) = [l for l in lr.async_get(hass).async_list_labels() if l.name == "FLARE"]
    registry = er.async_get(hass)
    assert label.label_id in registry.async_get("automation.kitchen_lighting").labels
    assert label.label_id in registry.async_get("automation.hall_lighting").labels


async def test_each_area_starts_on_the_schedule_named_like_its_floor(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    """Else on the first schedule."""
    _area(hass, "Kitchen", "light.k", floor="Downstairs")
    _area(hass, "Bedroom", "light.b", floor="Upstairs")
    _area(hass, "Loft", "light.l")

    result = await _first_setup(hass, ["Downstairs", "Upstairs"])
    assert _defaults(result) == {
        "set_up": "flare", "Kitchen": "schedule_1", "Bedroom": "schedule_2", "Loft": "schedule_1"
    }
    assert [o["value"] for o in _options(result, "Kitchen")] == ["skip", "schedule_1", "schedule_2"]

    result = await _submit(hass, result, {"areas": {"Kitchen": "schedule_1", "Bedroom": "schedule_2", "Loft": "skip"}})

    assert result["description_placeholders"] == {
        "schedules": "Downstairs, Upstairs", "zones": "2", "automations": "2", "flares": "2"
    }
    schedules = {s.title: s.subentry_id for s in schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))}
    followed = {a["alias"]: a["use_blueprint"]["input"]["schedule"] for a in _automations(automations_file)}
    assert followed == {
        "Kitchen Lighting": _device(hass, schedules["Downstairs"]),
        "Bedroom Lighting": _device(hass, schedules["Upstairs"]),
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
    assert result["description_placeholders"] == {"schedules": "Home", "zones": "0", "automations": "0", "flares": "0"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 3
    assert zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES)) == []


# --- Set up area, once FLARE exists --------------------------------------


async def _set_up_flare(hass: HomeAssistant, areas: list[str]) -> None:
    result = await _first_setup(hass, ["Home"])
    if result["type"] == "form":
        await _submit(hass, result, _choose(hass, result, areas))


async def test_set_up_area_lists_every_area_and_ticks_those_without_a_zone(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    kitchen = _area(hass, "Kitchen", "light.k")
    await _set_up_flare(hass, [kitchen])
    hall = _area(hass, "Hall", "light.h")

    result = await _start(hass)
    assert result["step_id"] == "areas"
    assert _picked(hass, result) == [hall]

    result = await _submit(hass, result, _choose(hass, result, [hall]))

    assert result["reason"] == "areas_set_up"
    assert result["description_placeholders"] == {"zones": "1", "automations": "1", "flares": "1"}
    assert sorted(a["alias"] for a in _automations(automations_file)) == ["Hall Lighting", "Kitchen Lighting"]


async def test_with_several_schedules_an_area_with_a_zone_starts_as_dont_set_up(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    _area(hass, "Kitchen", "light.k", floor="Upstairs")
    result = await _first_setup(hass, ["Downstairs", "Upstairs"])
    await _submit(hass, result, {"areas": {"Kitchen": "schedule_2"}})
    _area(hass, "Hall", "light.h", floor="Upstairs")

    result = await _start(hass)

    schedules = {s.title: s.subentry_id for s in schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))}
    assert _defaults(result) == {"set_up": "flare", "Hall": schedules["Upstairs"], "Kitchen": "skip"}


async def test_set_up_area_with_no_lights_in_areas_says_so(stub_entry_setup, automations_file, hass: HomeAssistant):
    await _set_up_flare(hass, [])

    result = await _start(hass)

    assert result["reason"] == "no_areas"


async def test_an_existing_zone_with_the_areas_name_is_reused(stub_entry_setup, automations_file, hass: HomeAssistant):
    await _set_up_flare(hass, [])
    zones = _entry_of_type(hass, ENTRY_TYPE_ZONES)
    result = await hass.config_entries.subentries.async_init((zones.entry_id, "state"), context={"source": "user"})
    await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Kitchen"})
    await hass.async_block_till_done()
    (zone,) = zone_instances(zones)
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _start(hass)
    assert _picked(hass, result) == [], "it has a zone, so it isn't ticked"
    result = await _submit(hass, result, _choose(hass, result, [kitchen]))

    assert result["description_placeholders"] == {"zones": "0", "automations": "1", "flares": "1"}
    assert [z.subentry_id for z in zone_instances(zones)] == [zone.subentry_id]
    (written,) = _automations(automations_file)
    assert written["use_blueprint"]["input"]["zone"] == _device(hass, zone.subentry_id)


async def test_an_area_can_get_just_a_zone(stub_entry_setup, automations_file, hass: HomeAssistant):
    """It starts unpicked next time, but can still be picked for the rest."""
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen], set_up="zone"))

    assert result["description_placeholders"] == {"schedules": "Home", "zones": "1", "automations": "0", "flares": "0"}
    assert [z.title for z in zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES))] == ["Kitchen"]
    assert _automations(automations_file) == []
    result = await _start(hass)
    assert _picked(hass, result) == []


async def test_an_area_can_get_a_zone_and_automation_without_a_flare(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen], set_up="automation"))

    assert result["description_placeholders"] == {"schedules": "Home", "zones": "1", "automations": "1", "flares": "0"}
    assert hass.states.get("automation.kitchen_lighting") is not None
    assert _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries == {}


# --- automations.yaml ----------------------------------------------------


async def test_the_users_own_automations_are_kept(stub_entry_setup, automations_file, hass: HomeAssistant):
    mine = {"id": "mine", "alias": "Mine", "triggers": [], "actions": []}
    automations_file.write_text(yaml.safe_dump([mine]))
    kitchen = _area(hass, "Kitchen", "light.k")

    await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen]))

    assert [a["alias"] for a in _automations(automations_file)] == ["Mine", "Kitchen Lighting"]


@pytest.mark.parametrize("text", ["mine: {}\n", "- id: [unclosed\n"], ids=["not a list", "not yaml"])
async def test_an_automations_file_it_cant_read_is_left_alone(stub_entry_setup, automations_file, hass: HomeAssistant, text):
    automations_file.write_text(text)
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen]))

    assert result["reason"] == "automations_invalid"
    assert automations_file.read_text() == text


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

    result = await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen]))

    assert result["reason"] == "automations_not_loaded"
    assert automations.read_text() == original
    assert _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries == {}


async def test_the_blueprint_is_installed_if_it_isnt_there(stub_entry_setup, automations_file, hass: HomeAssistant):
    installed = Path(hass.config.config_dir, "blueprints", "automation", BLUEPRINT_PATH)
    installed.unlink()
    from homeassistant.components.automation.helpers import async_get_blueprints

    await async_get_blueprints(hass).async_reset_cache()
    kitchen = _area(hass, "Kitchen", "light.k")

    await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen]))

    assert installed.exists()
    assert hass.states.get("automation.kitchen_lighting") is not None


async def test_an_entry_deleted_by_hand_is_created_again(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Only the missing one, and areas are offered as on first setup."""
    await _set_up_flare(hass, [])
    flares = _entry_of_type(hass, ENTRY_TYPE_FLARES)
    await hass.config_entries.async_remove(flares.entry_id)
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _start(hass)
    assert _picked(hass, result) == [kitchen]
    await _submit(hass, result, _choose(hass, result, [kitchen]))

    assert len(hass.config_entries.async_entries(DOMAIN)) == 3
    assert [f.title for f in _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries.values()] == ["Kitchen"]


async def test_set_up_area_needs_a_schedule(stub_entry_setup, hass: HomeAssistant):
    for entry_type in (ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_ZONES, ENTRY_TYPE_FLARES):
        MockConfigEntry(
            domain=DOMAIN, data={CONF_ENTRY_TYPE: entry_type}, unique_id=f"{DOMAIN}_{entry_type}", version=3
        ).add_to_hass(hass)

    result = await _start(hass)

    assert result["reason"] == "no_schedules"

