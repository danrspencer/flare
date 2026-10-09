"""The blueprint in a real HA automation engine, with FLARE's writing
services and scene.turn_on mocked: these tests are about what the blueprint
decides to call, for a given trigger and room state. The read-only
compute_scene_coverage is FLARE's own."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.flare.const import DOMAIN
from custom_components.flare.services.handlers import async_setup_services
from custom_components.flare.zone.claims import ClaimRegistry
from tests.functional.blueprint.harness import SENSOR


@pytest.fixture(autouse=True)
def scene_coverage_service(hass: HomeAssistant):
    """The real flare.compute_scene_coverage, and no other FLARE service."""
    entry = MockConfigEntry(domain=DOMAIN)
    async_setup_services(hass, entry, ClaimRegistry(hass, entry))
    for service in list(hass.services.async_services_for_domain(DOMAIN)):
        if service != "compute_scene_coverage":
            hass.services.async_remove(DOMAIN, service)


@pytest.fixture
def apply_lighting_calls(hass: HomeAssistant, scene_coverage_service):
    return async_mock_service(hass, "flare", "apply_lighting")


@pytest.fixture
def scene_turn_on_calls(hass: HomeAssistant):
    return async_mock_service(hass, "scene", "turn_on")


@pytest.fixture
def turn_off_calls(hass: HomeAssistant, scene_coverage_service):
    return async_mock_service(hass, "flare", "turn_off")


@pytest.fixture(autouse=True)
def claims_clear_calls(hass: HomeAssistant, scene_coverage_service):
    """Autouse: the blueprint releases handed-off lights on any tick."""
    return async_mock_service(hass, "flare", "claims_clear")


@pytest.fixture(autouse=True)
def adaptive_sensor(hass: HomeAssistant):
    """A plain state standing in for the schedule sensor, in Day (outside
    the default rgb_phases)."""
    hass.states.async_set(SENSOR, "Day", {"brightness": 200, "color_temp": 4000})


@pytest.fixture(autouse=True)
def _frozen(frozen_time):
    yield frozen_time


@pytest.fixture(autouse=True)
def expected_lingering_timers():
    """The automation's time_pattern timers are still scheduled at teardown."""
    return True
