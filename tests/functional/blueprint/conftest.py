"""The blueprint in a real HA automation engine, with FLARE's services and
scene.turn_on mocked: these tests are about what the blueprint decides to
call, for a given trigger and room state."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.functional.blueprint.harness import SENSOR


@pytest.fixture
def apply_lighting_calls(hass: HomeAssistant):
    return async_mock_service(hass, "flare", "apply_lighting")


@pytest.fixture
def scene_turn_on_calls(hass: HomeAssistant):
    return async_mock_service(hass, "scene", "turn_on")


@pytest.fixture
def turn_off_calls(hass: HomeAssistant):
    return async_mock_service(hass, "flare", "turn_off")


@pytest.fixture(autouse=True)
def claims_clear_calls(hass: HomeAssistant):
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
