"""Setting FLARE up, and then its areas: the integration page's main
button. Each area gets an automation from the blueprint in
automations.yaml, and then flares are offered for those rooms."""

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
    ENTRY_TYPE_SETTINGS,
)
from custom_components.flare.schedule.coordinator import schedule_instances
from tests.support import BLUEPRINT_PATH


def _area(
    hass: HomeAssistant, name: str, *lights: str, floor: str | None = None, level: int | None = None
) -> str:
    area = ar.async_get(hass).async_get_or_create(name)
    if floor is not None:
        floors = fr.async_get(hass)
        floor_id = (floors.async_get_floor_by_name(floor) or floors.async_create(floor, level=level)).floor_id
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
    """The device of a schedule subentry."""
    entry_id = next(e.entry_id for e in hass.config_entries.async_entries(DOMAIN) if subentry_id in e.subentries)
    return dr.async_get(hass).async_get_device_by_identifier((DOMAIN, subentry_id), entry_id).id


async def _start(hass: HomeAssistant):
    """The main flow: schedules the first time, areas after."""
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


async def _submit(
    hass: HomeAssistant, result, user_input: dict, *, set_up_automations: bool = True, skip_flares: bool = True
):
    """Submits a step. Past the schedules, the first setup asks whether to
    set up room automations, and past the areas whether to add flares; this
    says yes to automations and skips flares unless told otherwise."""
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done()
    if set_up_automations and result.get("step_id") == "automations":
        result = await _submit(hass, result, {"next_step_id": "areas"})
    if skip_flares and result.get("step_id") == "flares":
        result = await _submit(hass, result, {"next_step_id": "skip_flares"})
    return result


async def _add_flares(hass: HomeAssistant, result, picked: list[str] | None = None):
    """From the flares menu, the rooms list: all of it as offered, or the
    automations given."""
    assert (result["type"], result["step_id"]) == ("menu", "flares")
    result = await _submit(hass, result, {"next_step_id": "flare_rooms"})
    assert result["step_id"] == "flare_rooms"
    if picked is None:
        picked = result["data_schema"]({})["automation"]
    return await _submit(hass, result, {"automation": picked})


async def _first_setup(hass: HomeAssistant, names: list[str]):
    """Through the schedule steps with names of our own, to the areas form."""
    result = await _submit(hass, await _start(hass), {"layout": "custom"})
    return await _submit(hass, result, {"names": names})


def _layouts(result) -> list[tuple[str, str]]:
    """The schedules step's choices, as (value, label)."""
    (field,) = result["data_schema"].schema.values()
    return [(o["value"], o["label"]) for o in field.config["options"]]


def _schedule_titles(hass: HomeAssistant) -> list[str]:
    return [s.title for s in schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))]


def _summary(result) -> dict:
    """The first setup's summary, less its reload link."""
    return {k: v for k, v in result["description_placeholders"].items() if k != "reload"}


def _sections(result) -> dict[str, dict]:
    """Each section of areas (a floor's, or the floorless ones'), in order,
    with its fields by name."""
    return {key: {name: field for name, (_, field) in fields.items()} for key, fields in _section_keys(result).items()}


def _section_keys(result) -> dict[str, dict]:
    """As _sections, keeping each field's schema key, which holds its
    suggested value."""
    schema = result["data_schema"].schema
    return {str(k): {str(f): (f, v) for f, v in schema[k].schema.schema.items()} for k in schema}


def _area_fields(result) -> dict:
    """Every area's field, by name, whatever section it's in."""
    return {name: field for fields in _sections(result).values() for name, field in fields.items()}


def _defaults(result) -> dict:
    """Each area's suggested schedule, None for one that starts empty."""
    return {
        name: (key.description or {}).get("suggested_value")
        for fields in _section_keys(result).values()
        for name, (key, _) in fields.items()
    }


def _answer(result, choices: dict[str, str]) -> dict:
    """The areas form's input: each area by name on its choice, in its own
    section, and every other area left empty."""
    return {key: {f: choices[f] for f in fields if f in choices} for key, fields in _sections(result).items()}


def _choose(hass: HomeAssistant, result, area_ids: list[str]) -> dict:
    """The areas form's input: each area in `area_ids` on the one schedule,
    every other area left empty."""
    names = {ar.async_get(hass).async_get_area(a).name for a in area_ids}
    fields = _area_fields(result)
    (schedule,) = {o["value"] for o in _options(result, next(iter(fields)))} if fields else {None}
    return _answer(result, {f: schedule for f in fields if f in names})


def _options(result, field: str) -> list[dict]:
    return _area_fields(result)[field].config["options"]


def _picked(hass: HomeAssistant, result) -> list[str]:
    """The areas that start set up."""
    names = {a.name: a.id for a in ar.async_get(hass).async_list_areas()}
    return sorted(names[f] for f, v in _defaults(result).items() if v is not None)


# --- First setup -------------------------------------------------------


async def test_first_setup_gives_every_area_with_lights_an_automation(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    kitchen = _area(hass, "Kitchen", "light.k")
    hall = _area(hass, "Hall", "light.h")
    _area(hass, "Garage")

    result = await _start(hass)
    assert result["step_id"] == "schedules"
    result = await _submit(hass, result, {"layout": "home"})
    assert result["step_id"] == "areas"
    assert _picked(hass, result) == sorted([hall, kitchen]), "every area with lights starts set up"

    result = await _submit(hass, result, _choose(hass, result, [hall, kitchen]))

    assert result["reason"] == "setup_complete"
    assert _summary(result) == {
        "schedules": "Home", "automations": "2", "flares": "0"
    }
    (schedule,) = schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))
    written = {a["alias"]: a for a in _automations(automations_file)}
    assert written["Kitchen Lighting"]["use_blueprint"] == {
        "path": INSTALL_PATH,
        "input": {
            "schedule": _device(hass, schedule.subentry_id),
            "room_target": {"area_id": kitchen},
        },
    }
    assert hass.states.get("automation.kitchen_lighting") is not None
    assert er.async_get(hass).async_get("automation.kitchen_lighting").area_id == kitchen
    assert _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries == {}, "flares only when asked for"


async def test_its_automations_carry_a_flare_label(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Created once, and reused by a later run."""
    from homeassistant.helpers import label_registry as lr

    kitchen = _area(hass, "Kitchen", "light.k")
    hall = _area(hass, "Hall", "light.h")
    await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen]))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await _submit(hass, result, _choose(hass, result, [hall]))

    (label,) = [l for l in lr.async_get(hass).async_list_labels() if l.name == "FLARE"]
    assert (label.icon, label.color) == ("flare:logo", "amber")
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
    assert _defaults(result) == {"Kitchen": "schedule_1", "Bedroom": "schedule_2", "Loft": "schedule_1"}
    assert [o["value"] for o in _options(result, "Kitchen")] == ["schedule_1", "schedule_2"]

    result = await _submit(hass, result, _answer(result, {"Kitchen": "schedule_1", "Bedroom": "schedule_2"}))

    assert _summary(result) == {
        "schedules": "Downstairs, Upstairs", "automations": "2", "flares": "0"
    }
    schedules = {s.title: s.subentry_id for s in schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))}
    followed = {a["alias"]: a["use_blueprint"]["input"]["schedule"] for a in _automations(automations_file)}
    assert followed == {
        "Kitchen Lighting": _device(hass, schedules["Downstairs"]),
        "Bedroom Lighting": _device(hass, schedules["Upstairs"]),
    }


async def test_a_home_with_floors_is_offered_a_schedule_per_floor(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    """Named after the floors, lowest first, and each area starts on its
    own floor's. One for the whole home stays the default."""
    _area(hass, "Bedroom", "light.b", floor="Upstairs", level=1)
    _area(hass, "Kitchen", "light.k", floor="Downstairs", level=0)

    result = await _start(hass)
    assert _layouts(result) == [
        ("home", "home"), ("per_floor", "One per floor: Downstairs, Upstairs"), ("custom", "custom")
    ]
    assert result["data_schema"]({})["layout"] == "home"

    result = await _submit(hass, result, {"layout": "per_floor"})

    assert result["step_id"] == "areas"
    assert _defaults(result) == {"Kitchen": "schedule_1", "Bedroom": "schedule_2"}
    await _submit(hass, result, _answer(result, {}))
    assert _schedule_titles(hass) == ["Downstairs", "Upstairs"]


@pytest.mark.parametrize("floor", [None, "Ground"])
async def test_one_floor_or_none_is_offered_one_schedule_for_the_home(
    stub_entry_setup, automations_file, hass: HomeAssistant, floor: str | None
):
    _area(hass, "Kitchen", "light.k", floor=floor)

    result = await _start(hass)

    assert [value for value, _ in _layouts(result)] == ["home", "custom"]
    assert result["data_schema"]({})["layout"] == "home"
    result = await _submit(hass, result, {"layout": "home"})
    await _submit(hass, result, _answer(result, {}))
    assert _schedule_titles(hass) == ["Home"]


async def test_custom_names_start_from_one_for_the_home(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Not from the floors, which is what one per floor is for."""
    _area(hass, "Kitchen", "light.k", floor="Downstairs", level=0)
    _area(hass, "Bedroom", "light.b", floor="Upstairs", level=1)

    result = await _submit(hass, await _start(hass), {"layout": "custom"})

    assert result["step_id"] == "schedule_names"
    (field,) = result["data_schema"].schema
    assert field.description == {"suggested_value": ["Home"]}


async def test_chosen_names_make_the_schedules(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Blank entries are dropped, and there's no limit on how many."""
    names = ["Downstairs", " ", "Upstairs", "Loft", "Garden", "Annexe"]

    result = await _first_setup(hass, names)

    assert result["reason"] == "setup_complete"
    assert _schedule_titles(hass) == ["Downstairs", "Upstairs", "Loft", "Garden", "Annexe"]


async def test_areas_are_grouped_by_floor_lowest_first(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Floorless areas last, under Other areas, and a floor with no lights
    gets no section."""
    _area(hass, "Bedroom", "light.b", floor="Upstairs", level=1)
    _area(hass, "Loft", "light.l")
    _area(hass, "Kitchen", "light.k", floor="Downstairs", level=0)
    _area(hass, "Hall", "light.h", floor="Downstairs", level=0)
    _area(hass, "Shed", floor="Garden", level=-1)

    result = await _first_setup(hass, ["Home"])

    assert [(key, list(fields)) for key, fields in _sections(result).items()] == [
        ("Downstairs", ["Hall", "Kitchen"]), ("Upstairs", ["Bedroom"]), ("other_areas", ["Loft"])
    ]


async def test_a_home_without_floors_has_one_section_of_areas(stub_entry_setup, automations_file, hass: HomeAssistant):
    _area(hass, "Kitchen", "light.k")
    _area(hass, "Hall", "light.h")

    result = await _first_setup(hass, ["Home"])

    assert [(key, list(fields)) for key, fields in _sections(result).items()] == [("areas", ["Hall", "Kitchen"])]


async def test_areas_on_every_floor_are_set_up(stub_entry_setup, automations_file, hass: HomeAssistant):
    _area(hass, "Kitchen", "light.k", floor="Downstairs", level=0)
    _area(hass, "Bedroom", "light.b", floor="Upstairs", level=1)
    _area(hass, "Loft", "light.l")

    result = await _first_setup(hass, ["Home"])
    result = await _submit(hass, result, _answer(result, {"Kitchen": "schedule_1", "Bedroom": "schedule_1", "Loft": "schedule_1"}))

    assert sorted(a["alias"] for a in _automations(automations_file)) == [
        "Bedroom Lighting", "Kitchen Lighting", "Loft Lighting"
    ]


@pytest.mark.parametrize(
    ("names", "error"),
    [(["Up stairs", "up_stairs"], "duplicate_name"), (["Home", " !! "], "invalid_name"), ([" ", ""], "no_names")],
)
async def test_schedule_names_must_be_usable_and_distinct(
    stub_entry_setup, automations_file, hass: HomeAssistant, names: list[str], error: str
):
    result = await _first_setup(hass, names)

    assert (result["step_id"], result["errors"]) == ("schedule_names", {"names": error})
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_floors_whose_names_clash_go_to_naming_instead(stub_entry_setup, automations_file, hass: HomeAssistant):
    _area(hass, "Kitchen", "light.k", floor="Up stairs", level=0)
    _area(hass, "Bedroom", "light.b", floor="Up-stairs", level=1)

    result = await _submit(hass, await _start(hass), {"layout": "per_floor"})

    assert (result["step_id"], result["errors"]) == ("schedule_names", {"names": "duplicate_name"})
    (field,) = result["data_schema"].schema
    assert field.description == {"suggested_value": ["Up stairs", "Up-stairs"]}


async def test_a_house_with_no_lights_in_areas_still_gets_its_schedule(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    result = await _first_setup(hass, ["Home"])

    assert result["reason"] == "setup_complete"
    assert _summary(result) == {"schedules": "Home", "automations": "0", "flares": "0"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 3


async def test_first_setup_opens_on_the_schedules(stub_entry_setup, automations_file, hass: HomeAssistant):
    _area(hass, "Kitchen", "light.k")

    result = await _start(hass)

    assert (result["type"], result["step_id"]) == ("form", "schedules")

async def _set_up_flare(hass: HomeAssistant, areas: list[str]) -> None:
    result = await _first_setup(hass, ["Home"])
    if result["type"] == "form":
        await _submit(hass, result, _choose(hass, result, areas))


async def test_set_up_area_lists_every_area_and_ticks_those_not_set_up(
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
    assert result["description_placeholders"] == {"automations": "1", "flares": "0"}
    assert sorted(a["alias"] for a in _automations(automations_file)) == ["Hall Lighting", "Kitchen Lighting"]


async def test_with_several_schedules_an_area_already_set_up_starts_empty(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    _area(hass, "Kitchen", "light.k", floor="Upstairs")
    result = await _first_setup(hass, ["Downstairs", "Upstairs"])
    await _submit(hass, result, _answer(result, {"Kitchen": "schedule_2"}))
    _area(hass, "Hall", "light.h", floor="Upstairs")

    result = await _start(hass)

    schedules = {s.title: s.subentry_id for s in schedule_instances(_entry_of_type(hass, ENTRY_TYPE_SCHEDULES))}
    assert _defaults(result) == {"Hall": schedules["Upstairs"], "Kitchen": None}


async def test_set_up_area_with_no_lights_in_areas_says_so(stub_entry_setup, automations_file, hass: HomeAssistant):
    await _set_up_flare(hass, [])

    result = await _start(hass)

    assert result["reason"] == "no_areas"


async def test_an_area_counts_as_set_up_by_its_flare_labelled_automation(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    """Moving the automation to another area moves which area is set up."""
    kitchen = _area(hass, "Kitchen", "light.k")
    hall = _area(hass, "Hall", "light.h")
    await _set_up_flare(hass, [kitchen])
    assert _picked(hass, await _start(hass)) == [hall]

    er.async_get(hass).async_update_entity("automation.kitchen_lighting", area_id=hall)

    assert _picked(hass, await _start(hass)) == [kitchen]


async def test_skipping_flares_leaves_the_rooms_without_one(stub_entry_setup, automations_file, hass: HomeAssistant):
    kitchen = _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, (result := await _first_setup(hass, ["Home"])), _choose(hass, result, [kitchen]))

    assert _summary(result) == {"schedules": "Home", "automations": "1", "flares": "0"}
    assert hass.states.get("automation.kitchen_lighting") is not None
    assert _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries == {}


async def test_flares_are_offered_for_the_rooms_just_set_up(stub_entry_setup, automations_file, hass: HomeAssistant):
    """Every one ticked, named after its area."""
    kitchen = _area(hass, "Kitchen", "light.k")
    hall = _area(hass, "Hall", "light.h")
    result = await _first_setup(hass, ["Home"])

    result = await _submit(hass, result, _choose(hass, result, [kitchen, hall]), skip_flares=False)
    assert result["menu_options"] == ["flare_rooms", "skip_flares"]
    result = await _submit(hass, result, {"next_step_id": "flare_rooms"})

    (field,) = result["data_schema"].schema.values()
    assert [(o["value"], o["label"]) for o in field.config["options"]] == [
        ("automation.hall_lighting", "Hall"), ("automation.kitchen_lighting", "Kitchen")
    ]
    assert result["data_schema"]({})["automation"] == ["automation.hall_lighting", "automation.kitchen_lighting"]


async def test_each_room_picked_gets_a_flare(stub_entry_setup, automations_file, hass: HomeAssistant):
    kitchen = _area(hass, "Kitchen", "light.k")
    hall = _area(hass, "Hall", "light.h")
    result = await _first_setup(hass, ["Home"])
    result = await _submit(hass, result, _choose(hass, result, [kitchen, hall]), skip_flares=False)

    result = await _add_flares(hass, result, ["automation.kitchen_lighting"])

    assert _summary(result) == {"schedules": "Home", "automations": "2", "flares": "1"}
    assert [f.title for f in _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries.values()] == ["Kitchen"]


async def test_no_flares_are_offered_when_no_area_was_set_up(stub_entry_setup, automations_file, hass: HomeAssistant):
    _area(hass, "Kitchen", "light.k")
    result = await _first_setup(hass, ["Home"])

    result = await _submit(hass, result, _answer(result, {}), skip_flares=False)

    assert result["reason"] == "setup_complete"


async def test_first_setup_asks_before_setting_up_automations(stub_entry_setup, automations_file, hass: HomeAssistant):
    _area(hass, "Kitchen", "light.k")

    result = await _submit(hass, await _start(hass), {"layout": "home"}, set_up_automations=False)

    assert (result["type"], result["step_id"]) == ("menu", "automations")
    assert result["menu_options"] == ["areas", "schedules_only"]


async def test_skipping_automations_sets_up_the_schedules_alone(
    stub_entry_setup, automations_file, hass: HomeAssistant
):
    """For someone whose own automations drive their lights, to move a room
    at a time with Set up area."""
    _area(hass, "Kitchen", "light.k")
    result = await _submit(hass, await _start(hass), {"layout": "home"}, set_up_automations=False)

    result = await _submit(hass, result, {"next_step_id": "schedules_only"})

    assert result["reason"] == "schedules_set_up"
    assert result["description_placeholders"]["schedules"] == "Home"
    assert _schedule_titles(hass) == ["Home"]
    assert len(hass.config_entries.async_entries(DOMAIN)) == 3
    assert _automations(automations_file) == []


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
    await _add_flares(hass, await _submit(hass, result, _choose(hass, result, [kitchen]), skip_flares=False))

    assert len(hass.config_entries.async_entries(DOMAIN)) == 3
    assert [f.title for f in _entry_of_type(hass, ENTRY_TYPE_FLARES).subentries.values()] == ["Kitchen"]


async def test_set_up_area_needs_a_schedule(stub_entry_setup, hass: HomeAssistant):
    for entry_type in (ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_SETTINGS, ENTRY_TYPE_FLARES):
        MockConfigEntry(
            domain=DOMAIN, data={CONF_ENTRY_TYPE: entry_type}, unique_id=f"{DOMAIN}_{entry_type}", version=3
        ).add_to_hass(hass)

    result = await _start(hass)

    assert result["reason"] == "no_schedules"

