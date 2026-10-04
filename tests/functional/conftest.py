"""Functional tests run against a real Home Assistant instance, via
pytest-homeassistant-custom-component."""

import shutil
from pathlib import Path

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import mock_component

from tests.support import BLUEPRINT_FILE, BLUEPRINT_PATH, REPO_ROOT


@pytest.fixture
def hass_config_dir(tmp_path) -> str:
    """A throwaway config dir with this repo's custom_components/ symlinked
    in and the blueprint installed as a copy, so HA loads the real source
    while everything it writes lands in tmp_path."""
    (tmp_path / "custom_components").symlink_to(REPO_ROOT / "custom_components")
    installed = tmp_path / "blueprints" / "automation" / BLUEPRINT_PATH
    installed.parent.mkdir(parents=True)
    shutil.copy(BLUEPRINT_FILE, installed)
    return str(tmp_path)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def frozen_time():
    """Wall-clock control, for suites whose automations carry a live
    time_pattern trigger that could otherwise fire mid-test.

    real_asyncio=True is required: without it freezegun also freezes
    time.monotonic, which asyncio schedules timers on, and the loop hangs
    or fires timers out of order. Anchored two seconds past the minute,
    leaving ~58 real seconds before the next tick. Advance it with
    .tick()/.move_to(); never open a nested freeze_time."""
    anchor = dt_util.utcnow().replace(second=2, microsecond=0)
    with freeze_time(anchor, real_asyncio=True) as frozen:
        yield frozen


@pytest.fixture
def stub_entry_setup(hass: HomeAssistant):
    """Lets a real entry setup run without loading the frontend package."""
    mock_component(hass, "frontend")
    mock_component(hass, "repairs")
    hass.data.setdefault("frontend_extra_module_url", set())
    return hass


@pytest.fixture
async def automations_file(hass: HomeAssistant) -> Path:
    """automations.yaml, loaded the way HA's default configuration.yaml
    loads it, with the automation component set up."""
    Path(hass.config.config_dir, "configuration.yaml").write_text("automation: !include automations.yaml\n")
    assert await async_setup_component(hass, "automation", {})
    return Path(hass.config.config_dir, "automations.yaml")
