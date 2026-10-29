"""The config flows: adding schedule sensors and flares, the options flow,
and the migration to 2.0. Setting up FLARE and its areas is test_area_setup.py."""

import pytest
from homeassistant import loader
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
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
    ENTRY_TYPE_SETTINGS,
    SUBENTRY_TYPE_FLARE,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_ZONE,
)
from custom_components.flare.services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS


@pytest.fixture(autouse=True)
async def config_flow_loaded(hass: HomeAssistant) -> None:
    """An entry only reports its subentry types and options once FLARE's
    config flow is imported, which starting a flow would otherwise do."""
    await (await loader.async_get_integration(hass, DOMAIN)).async_get_platform("config_flow")


# --- Subentries and options ---------------------------------------------


def _entry(hass: HomeAssistant, entry_type: str, **kwargs) -> MockConfigEntry:
    kwargs = {"version": 3, "minor_version": 2, **kwargs}
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: entry_type}, unique_id=f"{DOMAIN}_{entry_type}", **kwargs)
    entry.add_to_hass(hass)
    return entry


async def _add_subentry(hass: HomeAssistant, entry, subentry_type: str, user_input: dict):
    result = await hass.config_entries.subentries.async_init((entry.entry_id, subentry_type), context={"source": "user"})
    assert result["type"] == "form"
    return await hass.config_entries.subentries.async_configure(result["flow_id"], user_input)


async def test_each_entry_offers_only_its_own_subentry_type(hass: HomeAssistant):
    schedules = _entry(hass, ENTRY_TYPE_SCHEDULES)
    settings = _entry(hass, ENTRY_TYPE_SETTINGS)
    flares = _entry(hass, ENTRY_TYPE_FLARES)
    assert set(schedules.supported_subentry_types) == {SUBENTRY_TYPE_SENSOR}
    assert set(settings.supported_subentry_types) == set()
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


async def test_the_options_flow_starts_from_the_shipped_patterns_and_saves_the_whole_list(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_SETTINGS)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    field = next(k for k in schema if k == CONF_TWO_STEP_MODELS)
    assert field.description["suggested_value"] == "\n".join(DEFAULT_TWO_STEP_MODEL_PATTERNS)

    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_TWO_STEP_MODELS: "*weird bulb*"})

    assert entry.options[CONF_TWO_STEP_MODELS] == "*weird bulb*"


async def test_the_options_flow_offers_the_minimum_change_starting_at_the_defaults(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_SETTINGS)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert entry.options[CONF_MIN_BRIGHTNESS_CHANGE] == DEFAULT_MIN_BRIGHTNESS_CHANGE
    assert entry.options[CONF_MIN_COLOR_TEMP_CHANGE] == DEFAULT_MIN_COLOR_TEMP_CHANGE

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MIN_BRIGHTNESS_CHANGE: 2.5, CONF_MIN_COLOR_TEMP_CHANGE: 0}
    )

    assert (entry.options[CONF_MIN_BRIGHTNESS_CHANGE], entry.options[CONF_MIN_COLOR_TEMP_CHANGE]) == (2.5, 0)


async def test_only_the_settings_entry_has_options(stub_entry_setup, hass: HomeAssistant):
    """Nothing reads the Schedules entry's options, so it doesn't offer any."""
    schedules = _entry(hass, ENTRY_TYPE_SCHEDULES)
    settings = _entry(hass, ENTRY_TYPE_SETTINGS)

    assert (schedules.supports_options, settings.supports_options) == (False, True)


# --- Migration to 2.0 ---------------------------------------------------


def _zone(title: str) -> ConfigSubentryData:
    return ConfigSubentryData(subentry_type=SUBENTRY_TYPE_ZONE, title=title, unique_id=title.lower(), data={})


async def test_upgrading_removes_the_zones_and_their_devices(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_SETTINGS, title="Zones", minor_version=1, subentries_data=[_zone("Kitchen")])
    (zone,) = entry.subentries
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, config_subentry_id=zone, identifiers={(DOMAIN, zone)}
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (entry.title, entry.minor_version, dict(entry.subentries)) == ("Settings", 2, {})
    assert dr.async_get(hass).async_get(device.id) is None


async def test_upgrading_keeps_a_title_someone_chose(stub_entry_setup, hass: HomeAssistant):
    entry = _entry(hass, ENTRY_TYPE_SETTINGS, title="Lighting", minor_version=1)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert (entry.title, entry.minor_version) == ("Lighting", 2)


async def test_upgrading_leaves_schedules_and_flares_as_they_are(stub_entry_setup, hass: HomeAssistant):
    schedules = _entry(
        hass,
        ENTRY_TYPE_SCHEDULES,
        title="Schedules",
        minor_version=1,
        subentries_data=[ConfigSubentryData(subentry_type=SUBENTRY_TYPE_SENSOR, title="Home", unique_id="home", data={})],
    )

    assert await hass.config_entries.async_setup(schedules.entry_id)

    assert (schedules.title, schedules.minor_version, len(schedules.subentries)) == ("Schedules", 2, 1)


async def test_a_new_install_gets_no_entries_at_startup(stub_entry_setup, hass: HomeAssistant):
    """Adding FLARE is still the user's choice."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries(DOMAIN) == []


