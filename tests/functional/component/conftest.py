import pytest
from homeassistant.core import HomeAssistant

from tests.functional.component.harness import setup_settings_entry


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """The Settings entry, set up."""
    await setup_settings_entry(hass)
    yield hass

