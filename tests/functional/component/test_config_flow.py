"""The config flows: adding the integration, adding schedule sensors and
tracking scopes, and the options flow."""

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
    ENTRY_TYPE_TRACKING,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_STATE,
)
from custom_components.flare.services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS
from custom_components.flare.tracking.scope import state_instances


def _light(hass: HomeAssistant, entity_id: str, *, area_id=None):
    created = er.async_get(hass).async_get_or_create("light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1])
    if area_id:
        er.async_get(hass).async_update_entity(created.entity_id, area_id=area_id)
    hass.states.async_set(entity_id, "on", {}, context=Context())


def _entry_of_type(hass: HomeAssistant, entry_type: str):
    return next(e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == entry_type)


async def test_setup_offers_one_state_device_per_area_that_has_lights(stub_entry_setup, hass: HomeAssistant):
    """A room is the unit almost everyone wants to track by, so the list
    arrives pre-selected rather than as a wall of work. Areas with no
    lights are left out - a scope that can never resolve anything is
    just an empty device to wonder about."""
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    hall = ar.async_get(hass).async_get_or_create("Hall")
    garage = ar.async_get(hass).async_get_or_create("Garage")
    _light(hass, "light.k", area_id=kitchen.id)
    _light(hass, "light.h", area_id=hall.id)
    # The Garage has entities, just no lights - so it must not be
    # offered. Without a non-light here, "lights only" would look
    # covered while actually being untested.
    door = er.async_get(hass).async_get_or_create("switch", "test", "garage_door")
    er.async_get(hass).async_update_entity(door.entity_id, area_id=garage.id)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    suggested = result["data_schema"]({})["areas"]
    assert sorted(suggested) == sorted([hall.id, kitchen.id])

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"areas": [kitchen.id]})

    assert result["type"] == "create_entry"
    scopes = state_instances(_entry_of_type(hass, ENTRY_TYPE_TRACKING))
    assert [s.title for s in scopes] == ["Kitchen"]


async def test_adding_the_integration_once_creates_both_entries(stub_entry_setup, hass: HomeAssistant):
    """Two entries is a grouping decision, not a reason to walk through
    Add Integration twice. The one the flow finishes on must be
    Schedules: HA's "integration added" dialog shows an unsuppressable
    rename + area form for every device on the completing flow's entry,
    and Tracking is the half that seeds a device per room."""
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    _light(hass, "light.k", area_id=kitchen.id)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"areas": [kitchen.id]})
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["title"] == "FLARE Schedules"
    assert {e.data[CONF_ENTRY_TYPE] for e in hass.config_entries.async_entries(DOMAIN)} == {
        ENTRY_TYPE_SCHEDULES,
        ENTRY_TYPE_TRACKING,
    }
    assert [s.title for s in state_instances(_entry_of_type(hass, ENTRY_TYPE_TRACKING))] == ["Kitchen"]


async def test_the_missing_half_can_be_added_back_on_its_own(stub_entry_setup, hass: HomeAssistant):
    """Deleting one entry has to be recoverable. With Schedules already
    present the flow creates only Tracking - and this time Tracking is
    what the flow itself returns, since there is no second entry to
    hand the visible completion to."""
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    _light(hass, "light.k", area_id=kitchen.id)
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}",
        version=3,
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"areas": [kitchen.id]})
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["title"] == "FLARE Zones"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_adding_it_again_with_both_present_aborts(stub_entry_setup, hass: HomeAssistant):
    """Nothing left to create, and neither half may be duplicated."""
    for entry_type in (ENTRY_TYPE_SCHEDULES, ENTRY_TYPE_TRACKING):
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


async def test_setup_with_no_areas_creates_the_entry_and_no_scopes(stub_entry_setup, hass: HomeAssistant):
    """Nothing here is required. With no areas there is nothing to
    offer, so both entries are created straight away and lights simply
    stay untracked until a state device exists."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert state_instances(_entry_of_type(hass, ENTRY_TYPE_TRACKING)) == []


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
    tracking = _entry(hass, ENTRY_TYPE_TRACKING)
    assert set(schedules.supported_subentry_types) == {SUBENTRY_TYPE_SENSOR}
    assert set(tracking.supported_subentry_types) == {SUBENTRY_TYPE_STATE}


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
    entry = _entry(hass, ENTRY_TYPE_TRACKING)

    result = await _add_subentry(hass, entry, SUBENTRY_TYPE_STATE, {"name": "Kitchen"})
    assert result["type"] == "create_entry"
    (subentry_id,) = entry.subentries

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Hall"})

    assert result["reason"] == "reconfigure_successful"
    assert [s.title for s in state_instances(entry)] == ["Hall"]


async def test_a_scope_name_already_in_use_is_refused(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_TRACKING)
    await _add_subentry(hass, entry, SUBENTRY_TYPE_STATE, {"name": "Kitchen"})

    result = await _add_subentry(hass, entry, SUBENTRY_TYPE_STATE, {"name": "kitchen"})

    assert result["errors"] == {"name": "already_configured"}


async def test_reconfiguring_a_scope_can_keep_its_own_name(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_TRACKING)
    await _add_subentry(hass, entry, SUBENTRY_TYPE_STATE, {"name": "Kitchen"})
    (subentry_id,) = entry.subentries

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Kitchen"})

    assert result["reason"] == "reconfigure_successful"


async def test_the_options_flow_starts_from_the_shipped_patterns_and_saves_the_whole_list(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_TRACKING)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    field = next(k for k in schema if k == CONF_TWO_STEP_MODELS)
    assert field.description["suggested_value"] == "\n".join(DEFAULT_TWO_STEP_MODEL_PATTERNS)

    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_TWO_STEP_MODELS: "*weird bulb*"})

    assert entry.options[CONF_TWO_STEP_MODELS] == "*weird bulb*"


async def test_the_options_flow_offers_the_minimum_change_starting_at_the_defaults(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_TRACKING)

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
    zones = _entry(hass, ENTRY_TYPE_TRACKING)

    assert (schedules.supports_options, zones.supports_options) == (False, True)
