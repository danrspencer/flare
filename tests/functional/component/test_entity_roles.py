"""The dashboard finds a schedule's entities by device and translation key,
and the Settings entry's by translation key alone. These are the keys the real entities register, the same
ones the dashboard tests' fixtures (tests/support/registry.py) assume."""

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_SETTINGS,
    SUBENTRY_TYPE_SENSOR,
)
from tests.support.registry import schedule_entities, settings_entities


async def _set_up(hass: HomeAssistant, entry_type: str, subentry_type: str | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: entry_type},
        unique_id=f"{DOMAIN}_{entry_type}",
        version=3,
        minor_version=2,
        subentries_data=(
            [ConfigSubentryData(subentry_type=subentry_type, title="Hall", unique_id="hall", data={})]
            if subentry_type
            else []
        ),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _roles(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return {
        e.translation_key: e.entity_id
        for e in er.async_entries_for_device(er.async_get(hass), device.id)
        if e.translation_key in _expected_roles(schedule_entities("device", "hall"))
    }


def _expected_roles(entities: dict) -> set[str]:
    return {e["translation_key"] for e in entities.values()}


def _as_roles(entities: dict) -> dict[str, str]:
    return {e["translation_key"]: e["entity_id"] for e in entities.values()}


async def test_a_schedules_entities_carry_the_roles_the_dashboard_reads(stub_entry_setup, hass: HomeAssistant):
    entry = await _set_up(hass, ENTRY_TYPE_SCHEDULES, SUBENTRY_TYPE_SENSOR)

    assert _roles(hass, entry) == _as_roles(schedule_entities("device", "hall"))


async def test_the_settings_entitys_carry_the_roles_the_dashboard_reads(stub_entry_setup, hass: HomeAssistant):
    entry = await _set_up(hass, ENTRY_TYPE_SETTINGS)

    roles = {
        e.translation_key: e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.translation_key in _expected_roles(settings_entities())
    }
    assert roles == _as_roles(settings_entities())


async def test_a_schedules_entities_take_their_names_from_the_translations(stub_entry_setup, hass: HomeAssistant):
    entry = await _set_up(hass, ENTRY_TYPE_SCHEDULES, SUBENTRY_TYPE_SENSOR)
    roles = _roles(hass, entry)

    names = {role: hass.states.get(roles[role]).name for role in roles}

    assert names["morning_brightness"] == "Hall Morning Brightness"
    assert names["day_kelvin_transition"] == "Hall Day Colour Transition"
    assert names["evening_earliest_time"] == "Hall Evening Earliest"
    assert names["phase_override"] == "Hall Phase"
    assert names["sticky_phase_override"] == "Hall Sticky Phase Override"
    assert hass.states.get("event.hall_flare_phase").name == "Hall Phase"
