import pytest
from homeassistant.core import HomeAssistant

from tests.functional.component.harness import setup_zones_entry


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """A Zones entry with one zone, "Test Zone"."""
    await setup_zones_entry(hass)
    yield hass

