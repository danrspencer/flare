import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import mock_component

from tests.functional.component.harness import setup_tracking_entry


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """A Tracking entry with one scope, "Test Scope"."""
    await setup_tracking_entry(hass)
    yield hass


@pytest.fixture
def stub_entry_setup(hass: HomeAssistant):
    """Lets a real entry setup run without loading the frontend package."""
    mock_component(hass, "frontend")
    mock_component(hass, "repairs")
    hass.data.setdefault("frontend_extra_module_url", set())
    return hass
