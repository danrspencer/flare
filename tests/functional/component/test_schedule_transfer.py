"""Exporting and importing a schedule: flare.export_schedule,
flare.import_schedule, and the same through a schedule's Reconfigure."""

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SCHEDULES, SUBENTRY_TYPE_SENSOR
from custom_components.flare.schedule.transfer import parse


@pytest.fixture
async def entry(stub_entry_setup, hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}",
        version=3,
        subentries_data=[
            ConfigSubentryData(subentry_type=SUBENTRY_TYPE_SENSOR, title=title, unique_id=slug, data={})
            for title, slug in (("Downstairs", "downstairs"), ("Upstairs", "upstairs"))
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _device(hass: HomeAssistant, entry: MockConfigEntry, title: str) -> str:
    subentry_id = next(s.subentry_id for s in entry.subentries.values() if s.title == title)
    return dr.async_get(hass).async_get_device_by_identifier((DOMAIN, subentry_id), entry.entry_id).id


def _subentry(entry: MockConfigEntry, title: str) -> str:
    return next(s.subentry_id for s in entry.subentries.values() if s.title == title)


async def _export(hass: HomeAssistant, device_id: str) -> str:
    response = await hass.services.async_call(
        DOMAIN, "export_schedule", {"schedule_device_id": device_id}, blocking=True, return_response=True
    )
    return response["schedule"]


async def _import(hass: HomeAssistant, device_id: str, schedule) -> None:
    await hass.services.async_call(
        DOMAIN, "import_schedule", {"schedule_device_id": device_id, "schedule": schedule}, blocking=True
    )


async def test_export_gives_every_value_keyed_by_phase(entry, hass: HomeAssistant):
    text = await _export(hass, _device(hass, entry, "Downstairs"))

    assert len(parse(text)) == 21
    assert 'evening:\n  earliest: "17:00"\n  latest: "20:00"\n' in text


async def test_import_sets_only_what_it_names(entry, hass: HomeAssistant):
    device = _device(hass, entry, "Downstairs")

    await _import(hass, device, 'morning:\n  time: "06:30"\nnight:\n  kelvin: 2000\n')

    assert hass.states.get("time.downstairs_morning_time").state == "06:30:00"
    assert float(hass.states.get("number.downstairs_night_kelvin").state) == 2000
    assert hass.states.get("time.downstairs_day_time").state == "08:00:00"


async def test_an_unquoted_time_is_still_a_time(entry, hass: HomeAssistant):
    """YAML 1.1 reads a bare 21:30 as the base-60 number 1290."""
    await _import(hass, _device(hass, entry, "Downstairs"), "night:\n  time: 21:30\n")

    assert hass.states.get("time.downstairs_night_time").state == "21:30:00"


async def test_a_schedule_with_a_mistake_changes_nothing(entry, hass: HomeAssistant):
    """Checked in full before any value is set."""
    device = _device(hass, entry, "Downstairs")
    before = await _export(hass, device)

    with pytest.raises(ServiceValidationError, match="night.brightness"):
        await _import(hass, device, 'morning:\n  time: "05:00"\nnight:\n  brightness: 900\n')

    assert await _export(hass, device) == before


async def test_one_schedule_copies_onto_another(entry, hass: HomeAssistant):
    downstairs, upstairs = _device(hass, entry, "Downstairs"), _device(hass, entry, "Upstairs")
    await _import(hass, downstairs, 'day:\n  brightness: 200\nevening:\n  latest: "21:15"\n')

    await _import(hass, upstairs, await _export(hass, downstairs))

    assert await _export(hass, upstairs) == await _export(hass, downstairs)


async def test_a_mapping_in_service_data_is_accepted(entry, hass: HomeAssistant):
    """As written straight into an automation's YAML."""
    await _import(hass, _device(hass, entry, "Downstairs"), {"evening": {"brightness": 120}})

    assert float(hass.states.get("number.downstairs_evening_brightness").state) == 120


async def test_a_device_that_is_not_a_schedule_is_refused(entry, hass: HomeAssistant):
    other = MockConfigEntry(domain="test")
    other.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id, identifiers={("test", "x")})

    with pytest.raises(ServiceValidationError):
        await _export(hass, device.id)


async def test_reconfigure_shows_the_schedule_and_imports_a_replacement(entry, hass: HomeAssistant):
    subentry_id = _subentry(entry, "Downstairs")
    exported = await _export(hass, _device(hass, entry, "Downstairs"))

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    shown = next(k for k in result["data_schema"].schema if k == "schedule").description["suggested_value"]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"schedule": shown.replace('time: "22:00"', 'time: "23:15"')}
    )

    assert shown == exported
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "schedule_imported"
    assert hass.states.get("time.downstairs_night_time").state == "23:15:00"


async def test_reconfigure_explains_a_mistake_and_changes_nothing(entry, hass: HomeAssistant):
    subentry_id = _subentry(entry, "Downstairs")
    before = await _export(hass, _device(hass, entry, "Downstairs"))

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"schedule": "evening:\n  time: \"18:00\"\n"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"schedule": "invalid_schedule"}
    assert "evening.time" in result["description_placeholders"]["error"]
    assert await _export(hass, _device(hass, entry, "Downstairs")) == before


async def test_a_renamed_entity_is_still_the_schedules(entry, hass: HomeAssistant):
    """Found by its unique ID, for export, import and the schedule itself."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.util import dt as dt_util

    registry = er.async_get(hass)
    registry.async_update_entity("time.downstairs_morning_time", new_entity_id="time.wake_up")
    registry.async_update_entity("number.downstairs_night_kelvin", new_entity_id="number.bedtime_warmth")
    await hass.async_block_till_done()
    device = _device(hass, entry, "Downstairs")

    await _import(hass, device, {"morning": {"time": "05:30"}, "night": {"kelvin": 2100}})
    await hass.data[DOMAIN][_subentry(entry, "Downstairs")].async_refresh()

    assert hass.states.get("time.wake_up").state == "05:30:00"
    assert 'morning:\n  time: "05:30"' in await _export(hass, device)
    assert "2100" in await _export(hass, device)
    morning = dt_util.as_local(dt_util.utc_from_timestamp(hass.states.get("sensor.downstairs_flare").attributes["morning_start"]))
    assert (morning.hour, morning.minute) == (5, 30)


async def test_a_value_that_cant_be_read_is_left_out_of_the_export(entry, hass: HomeAssistant):
    """As the curve leaves it out (and uses its default)."""
    hass.states.async_set("number.downstairs_morning_kelvin", "not a number")
    hass.states.async_set("time.downstairs_day_time", "unavailable")

    values = parse(await _export(hass, _device(hass, entry, "Downstairs")))

    assert len(values) == 19
    assert "morning_kelvin" not in values and "day_time" not in values
