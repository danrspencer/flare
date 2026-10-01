"""The config flows: adding the integration, adding schedule sensors and
zones, and the options flow."""

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TWO_STEP_MODELS,
    DEFAULT_MIN_BRIGHTNESS_CHANGE,
    DEFAULT_MIN_COLOR_TEMP_CHANGE,
    DOMAIN,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_ZONES,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_ZONE,
)
from custom_components.flare.services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS
from custom_components.flare.zone.instance import zone_instances


def _light(hass: HomeAssistant, entity_id: str, *, area_id=None):
    created = er.async_get(hass).async_get_or_create("light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1])
    if area_id:
        er.async_get(hass).async_update_entity(created.entity_id, area_id=area_id)
    hass.states.async_set(entity_id, "on", {}, context=Context())


def _entry_of_type(hass: HomeAssistant, entry_type: str):
    return next(e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == entry_type)


async def test_setup_offers_one_zone_per_area_that_has_lights(stub_entry_setup, hass: HomeAssistant):
    """Pre-selected, so the common case is one click. Areas with no lights
    are left out: a zone there could never drive anything."""
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    hall = ar.async_get(hass).async_get_or_create("Hall")
    garage = ar.async_get(hass).async_get_or_create("Garage")
    _light(hass, "light.k", area_id=kitchen.id)
    _light(hass, "light.h", area_id=hall.id)
    # Entities, just no lights. Without one, "lights only" would look
    # covered while untested.
    door = er.async_get(hass).async_get_or_create("switch", "test", "garage_door")
    er.async_get(hass).async_update_entity(door.entity_id, area_id=garage.id)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    assert sorted(result["data_schema"]({})["areas"]) == sorted([hall.id, kitchen.id])

    await hass.config_entries.flow.async_configure(result["flow_id"], {"schedule": "Home", "areas": [kitchen.id]})
    await hass.async_block_till_done()

    assert [z.title for z in zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES))] == ["Kitchen"]


async def test_adding_the_integration_once_gives_a_working_schedule_and_zones(stub_entry_setup, hass: HomeAssistant):
    """Both entries, a first schedule with its entities, and a zone per room.
    The flow ends on a summary rather than on either entry: HA's
    "integration added" dialog would prompt to rename and place every
    device the entry it completes on has."""
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    _light(hass, "light.k", area_id=kitchen.id)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["data_schema"]({})["schedule"] == "Home"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"schedule": "Downstairs", "areas": [kitchen.id]}
    )
    await hass.async_block_till_done()

    assert result["type"] == "abort" and result["reason"] == "setup_complete"
    assert result["description_placeholders"] == {"created": "a schedule called Downstairs and 1 zone"}
    assert {e.data[CONF_ENTRY_TYPE] for e in hass.config_entries.async_entries(DOMAIN)} == {
        ENTRY_TYPE_SCHEDULES,
        ENTRY_TYPE_ZONES,
    }
    assert hass.states.get("sensor.downstairs_flare").state in ("Morning", "Day", "Evening", "Night")
    assert [z.title for z in zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES))] == ["Kitchen"]


async def test_a_schedule_name_with_nothing_to_name_entities_after_is_refused(stub_entry_setup, hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"schedule": " !! "})

    assert result["type"] == "form"
    assert result["errors"] == {"schedule": "invalid_name"}
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_the_missing_zones_can_be_added_back_on_their_own(stub_entry_setup, hass: HomeAssistant):
    """Deleting one entry has to be recoverable, and only that half is
    created again."""
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    _light(hass, "light.k", area_id=kitchen.id)
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}",
        version=3,
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "schedule" not in result["data_schema"]({})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"areas": [kitchen.id]})
    await hass.async_block_till_done()

    assert result["description_placeholders"] == {"created": "1 zone"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_the_missing_schedules_can_be_added_back_with_a_first_schedule(stub_entry_setup, hass: HomeAssistant):
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES},
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_ZONES}",
        version=3,
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "areas" not in result["data_schema"]({})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"schedule": "Home"})
    await hass.async_block_till_done()

    assert result["description_placeholders"] == {"created": "a schedule called Home"}
    schedules = _entry_of_type(hass, ENTRY_TYPE_SCHEDULES)
    assert [s.title for s in schedules.subentries.values()] == ["Home"]


async def test_adding_it_again_with_both_present_aborts(stub_entry_setup, hass: HomeAssistant):
    """Nothing left to create, and neither half may be duplicated."""
    for entry_type in (ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_ZONES):
        MockConfigEntry(
            domain=DOMAIN,
            data={CONF_ENTRY_TYPE: entry_type},
            unique_id=f"{DOMAIN}_{entry_type}",
            version=3,
        ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_setup_with_no_areas_still_creates_a_schedule_and_no_zones(stub_entry_setup, hass: HomeAssistant):
    """With no areas there are no rooms to offer; lights stay untracked
    until a zone exists."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "areas" not in result["data_schema"]({})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"schedule": "Home"})
    await hass.async_block_till_done()

    assert result["description_placeholders"] == {"created": "a schedule called Home and 0 zones"}
    assert zone_instances(_entry_of_type(hass, ENTRY_TYPE_ZONES)) == []


# --- Subentries and options ---------------------------------------------


def _entry(hass: HomeAssistant, entry_type: str, **kwargs) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: entry_type}, unique_id=f"{DOMAIN}_{entry_type}", version=3, **kwargs)
    entry.add_to_hass(hass)
    return entry


async def _add_subentry(hass: HomeAssistant, entry, subentry_type: str, user_input: dict):
    result = await hass.config_entries.subentries.async_init((entry.entry_id, subentry_type), context={"source": "user"})
    assert result["type"] == "form"
    return await hass.config_entries.subentries.async_configure(result["flow_id"], user_input)


async def test_each_entry_offers_only_its_own_subentry_type(hass: HomeAssistant):
    schedules = _entry(hass, ENTRY_TYPE_SCHEDULES)
    zones = _entry(hass, ENTRY_TYPE_ZONES)
    assert set(schedules.supported_subentry_types) == {SUBENTRY_TYPE_SENSOR}
    assert set(zones.supported_subentry_types) == {SUBENTRY_TYPE_ZONE}


async def test_adding_a_schedule_sensor(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_SCHEDULES)

    result = await _add_subentry(hass, entry, SUBENTRY_TYPE_SENSOR, {"name": "Ground Floor"})

    assert result["type"] == "create_entry"
    assert [(s.title, s.unique_id) for s in entry.subentries.values()] == [("Ground Floor", "ground_floor")]


async def test_a_schedule_name_already_in_use_is_refused(stub_entry_setup, hass: HomeAssistant):
    """Compared slugified, since the slug is the entity_id prefix."""
    entry = _entry(hass, ENTRY_TYPE_SCHEDULES)
    await _add_subentry(hass, entry, SUBENTRY_TYPE_SENSOR, {"name": "Ground Floor"})

    result = await _add_subentry(hass, entry, SUBENTRY_TYPE_SENSOR, {"name": "ground  floor"})

    assert result["errors"] == {"name": "already_configured"}
    assert len(entry.subentries) == 1


async def test_adding_and_renaming_a_zone(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_ZONES)

    result = await _add_subentry(hass, entry, SUBENTRY_TYPE_ZONE, {"name": "Kitchen"})
    assert result["type"] == "create_entry"
    (subentry_id,) = entry.subentries

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Hall"})

    assert result["reason"] == "reconfigure_successful"
    assert [s.title for s in zone_instances(entry)] == ["Hall"]


async def test_a_zone_name_already_in_use_is_refused(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_ZONES)
    await _add_subentry(hass, entry, SUBENTRY_TYPE_ZONE, {"name": "Kitchen"})

    result = await _add_subentry(hass, entry, SUBENTRY_TYPE_ZONE, {"name": "kitchen"})

    assert result["errors"] == {"name": "already_configured"}


async def test_reconfiguring_a_zone_can_keep_its_own_name(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_ZONES)
    await _add_subentry(hass, entry, SUBENTRY_TYPE_ZONE, {"name": "Kitchen"})
    (subentry_id,) = entry.subentries

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Kitchen"})

    assert result["reason"] == "reconfigure_successful"


async def test_the_options_flow_starts_from_the_shipped_patterns_and_saves_the_whole_list(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_ZONES)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    field = next(k for k in schema if k == CONF_TWO_STEP_MODELS)
    assert field.description["suggested_value"] == "\n".join(DEFAULT_TWO_STEP_MODEL_PATTERNS)

    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_TWO_STEP_MODELS: "*weird bulb*"})

    assert entry.options[CONF_TWO_STEP_MODELS] == "*weird bulb*"


async def test_the_options_flow_offers_the_minimum_change_starting_at_the_defaults(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_ZONES)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert entry.options[CONF_MIN_BRIGHTNESS_CHANGE] == DEFAULT_MIN_BRIGHTNESS_CHANGE
    assert entry.options[CONF_MIN_COLOR_TEMP_CHANGE] == DEFAULT_MIN_COLOR_TEMP_CHANGE

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MIN_BRIGHTNESS_CHANGE: 2.5, CONF_MIN_COLOR_TEMP_CHANGE: 0}
    )

    assert (entry.options[CONF_MIN_BRIGHTNESS_CHANGE], entry.options[CONF_MIN_COLOR_TEMP_CHANGE]) == (2.5, 0)


async def test_only_the_zones_entry_has_options(stub_entry_setup, hass: HomeAssistant):
    """Nothing reads the Schedules entry's options, so it doesn't offer any."""
    schedules = _entry(hass, ENTRY_TYPE_SCHEDULES)
    zones = _entry(hass, ENTRY_TYPE_ZONES)

    assert (schedules.supports_options, zones.supports_options) == (False, True)
