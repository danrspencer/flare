"""The dashboard finds a schedule's and a zone's entities by device and
translation key. These are the keys the real entities register, the same
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
    ENTRY_TYPE_ZONES,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_ZONE,
)
from tests.support.registry import schedule_entities, zone_entities


async def _set_up(hass: HomeAssistant, entry_type: str, subentry_type: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: entry_type},
        unique_id=f"{DOMAIN}_{entry_type}",
        version=3,
        subentries_data=[ConfigSubentryData(subentry_type=subentry_type, title="Hall", unique_id="hall", data={})],
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
        if e.translation_key in _expected_roles(schedule_entities) | _expected_roles(zone_entities)
    }


def _expected_roles(make) -> set[str]:
    return {e["translation_key"] for e in make("device", "hall").values()}


def _as_roles(entities: dict) -> dict[str, str]:
    return {e["translation_key"]: e["entity_id"] for e in entities.values()}


async def test_a_schedules_entities_carry_the_roles_the_dashboard_reads(stub_entry_setup, hass: HomeAssistant):
    entry = await _set_up(hass, ENTRY_TYPE_SCHEDULES, SUBENTRY_TYPE_SENSOR)

    assert _roles(hass, entry) == _as_roles(schedule_entities("device", "hall"))


async def test_a_zones_entities_carry_the_roles_the_dashboard_reads(stub_entry_setup, hass: HomeAssistant):
    entry = await _set_up(hass, ENTRY_TYPE_ZONES, SUBENTRY_TYPE_ZONE)

    assert _roles(hass, entry) == _as_roles(zone_entities("device", "hall"))
