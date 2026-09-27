"""Behaviour tests: what FLARE does, end to end. The real blueprint, the
real schedule and services, and HA's real light component - only the
bulbs are fake.
Tests are named for the capability, not the code path.

Every blueprint run's trace is written to trace-dumps/ for CI to render.
"""

from typing import Any

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, setup_test_component_platform

from tests.functional.behaviour.harness import (
    CURVE_BRIGHTNESS,
    CURVE_KELVIN,
    SCHEDULE_SENSOR,
    START,
    SUNSET,
    TRACE_DIR,
    FakeBulb,
    dump_traces,
    setup_schedule,
    setup_tracking_entry,
    today_at,
)
from tests.support import BLUEPRINT_PATH


@pytest.fixture
def frozen_time(hass: HomeAssistant):
    """The pinned day's clock, starting at START local time. After `hass`,
    which sets the time zone."""
    with freeze_time(today_at(START), real_asyncio=True) as frozen:
        yield frozen


@pytest.fixture(autouse=True)
async def schedule(stub_entry_setup, frozen_time, hass: HomeAssistant):
    """The real schedule the room follows, on the pinned day."""
    hass.states.async_set("sun.sun", "below_horizon", {"next_setting": today_at(SUNSET).isoformat()})
    entry = await setup_schedule(hass)
    state = hass.states.get(SCHEDULE_SENSOR)
    assert (state.state, state.attributes["brightness"], state.attributes["color_temp"]) == (
        "Evening",
        CURVE_BRIGHTNESS,
        CURVE_KELVIN,
    ), "the pinned day isn't where the tests expect it"
    return entry


@pytest.fixture(autouse=True)
def expected_lingering_timers():
    """The automation's time_pattern timers are still scheduled at teardown."""
    return True


@pytest.fixture(params=[False, True], ids=["untracked", "tracked"])
async def tracking_scope(request, hass: HomeAssistant) -> str | None:
    """The real Tracking entry, run twice: without a scope, and with one
    over the room. Returns the scope's area id (for add_bulbs), or None.
    Use this or `tracked_scope` or `flare`, never two of them."""
    _entry, area_id = await setup_tracking_entry(hass, tracked=request.param)
    return area_id


@pytest.fixture
async def tracked_scope(hass: HomeAssistant) -> str:
    """For tests that are themselves about tracking: always a scope."""
    _entry, area_id = await setup_tracking_entry(hass, tracked=True)
    return area_id


@pytest.fixture
async def flare(hass: HomeAssistant) -> MockConfigEntry:
    """The real Tracking entry with no scope."""
    entry, _ = await setup_tracking_entry(hass, tracked=False)
    return entry


@pytest.fixture(autouse=True)
def capture_trace(request, hass: HomeAssistant):
    """Writes the run's automation traces at teardown. Depends on `hass`
    so it tears down first, while the traces still exist."""
    yield
    dump_traces(
        hass,
        TRACE_DIR,
        test_id=request.node.nodeid,
        outcome="failed" if getattr(request.node, "behaviour_failed", False) else "passed",
        filename=request.node.name,
    )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Records a failed test on its item, for capture_trace."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        item.behaviour_failed = True


@pytest.fixture
def add_bulbs(hass: HomeAssistant):
    """add_bulbs(*names, area_id=None, **{name: overrides}) registers fake
    bulbs with HA's real light component. Call once per test.

    Overrides are FakeBulb options, plus `device` ({"manufacturer",
    "model"}) to link the bulb to a real device - added by hand, since a
    YAML-configured platform never acts on device_info."""

    async def _add(*names: str, area_id: str | None = None, **overrides: dict) -> list[FakeBulb]:
        bulbs = [FakeBulb(name, **{k: v for k, v in overrides.get(name, {}).items() if k != "device"}) for name in names]
        setup_test_component_platform(hass, "light", bulbs)
        assert await async_setup_component(hass, "light", {"light": {"platform": "test"}})
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        owner = None
        for bulb in bulbs:
            assert bulb.entity_id, f"{bulb.name} never got an entity_id"
            if area_id is not None:
                registry.async_update_entity(bulb.entity_id, area_id=area_id)
            device = overrides.get(bulb.name, {}).get("device")
            if device is None:
                continue
            if owner is None:
                owner = MockConfigEntry(domain="test")
                owner.add_to_hass(hass)
            device_entry = dr.async_get(hass).async_get_or_create(
                config_entry_id=owner.entry_id,
                identifiers={("test", bulb.unique_id)},
                manufacturer=device["manufacturer"],
                model=device["model"],
                name=bulb.name,
            )
            registry.async_update_entity(bulb.entity_id, device_id=device_entry.id)
        return bulbs

    return _add


@pytest.fixture
def setup_room(hass: HomeAssistant):
    """setup_room(lights=..., occupancy_sensors=..., **inputs): a real
    automation from the blueprint. Unset inputs take their defaults."""

    async def _setup(*, lights: list[FakeBulb | str], occupancy_sensors: list[str] | None = None, **inputs: Any) -> None:
        entity_ids = [light if isinstance(light, str) else light.entity_id for light in lights]
        target = entity_ids + list(occupancy_sensors or [])
        input_ = {"adaptive_sensor": SCHEDULE_SENSOR, "room_target": {"entity_id": target}, **inputs}
        assert await async_setup_component(
            hass,
            "automation",
            # A stable id, so the trace is keyed automation.room.
            {"automation": [{"id": "room", "alias": "room", "use_blueprint": {"path": BLUEPRINT_PATH, "input": input_}}]},
        )
        await hass.async_block_till_done()
        assert hass.states.get("automation.room") is not None, "the automation failed to set up from the blueprint"

    return _setup
