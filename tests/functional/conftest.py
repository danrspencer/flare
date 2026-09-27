"""Functional tests run against a real Home Assistant instance, via
pytest-homeassistant-custom-component."""

import pytest
from freezegun import freeze_time
from homeassistant.util import dt as dt_util

from tests.support import REPO_ROOT


@pytest.fixture
def hass_config_dir(tmp_path) -> str:
    """A throwaway config dir with this repo's custom_components/ and
    blueprints/ symlinked in, so HA loads the real source while everything
    it writes lands in tmp_path."""
    (tmp_path / "custom_components").symlink_to(REPO_ROOT / "custom_components")
    (tmp_path / "blueprints").symlink_to(REPO_ROOT / "blueprints")
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
