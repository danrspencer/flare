"""The config flows: adding schedule sensors, zones and flares, and the
options flow. Setting up FLARE and its areas is test_area_setup.py."""

import pytest
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    CONF_TWO_STEP_MODELS,
    DEFAULT_MIN_BRIGHTNESS_CHANGE,
    DEFAULT_MIN_COLOR_TEMP_CHANGE,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_ZONES,
    SUBENTRY_TYPE_FLARE,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_ZONE,
)
from custom_components.flare.services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS
from custom_components.flare.zone.instance import zone_instances


@pytest.fixture(autouse=True)
async def config_flow_loaded(hass: HomeAssistant) -> None:
    """An entry only reports its subentry types and options once FLARE's
    config flow is imported, which starting a flow would otherwise do."""
    await (await loader.async_get_integration(hass, DOMAIN)).async_get_platform("config_flow")


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
    flares = _entry(hass, ENTRY_TYPE_FLARES)
    assert set(schedules.supported_subentry_types) == {SUBENTRY_TYPE_SENSOR}
    assert set(zones.supported_subentry_types) == {SUBENTRY_TYPE_ZONE}
    assert set(flares.supported_subentry_types) == {SUBENTRY_TYPE_FLARE}


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


async def test_a_new_install_gets_no_entries_at_startup(stub_entry_setup, hass: HomeAssistant):
    """Adding FLARE is still the user's choice."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries(DOMAIN) == []


