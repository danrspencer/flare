import pytest
from homeassistant.core import HomeAssistant

from tests.functional.component.harness import setup_tracking_entry


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """A Tracking entry with one scope, "Test Scope"."""
    await setup_tracking_entry(hass)
    yield hass

