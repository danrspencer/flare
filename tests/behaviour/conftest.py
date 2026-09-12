"""
Behaviour tests: what FLARE *does*, named as the capability being
tested rather than as the code path taken. The real blueprint, the real
flare services, HA's real light component - only the bulbs are fake,
standing in for the Zigbee radio and nothing else.

Contrast tests/integration/test_blueprint.py, which mocks
flare.apply_lighting / scene.turn_on / light.turn_off and so asserts on
recorded service calls. That layer can prove the blueprint *decided* to
do something; it structurally cannot prove a light ended up at a
brightness, because nothing downstream of the decision runs. Every live
bug found this session lived in exactly that seam - blueprint and
services were each correct alone and wrong together.

Deliberately the same hass_config_dir/enable_custom_integrations setup
as tests/integration/conftest.py - see that file for why each is
needed. Duplicated rather than shared because a conftest is the one
thing pytest resolves per-directory, and a cross-directory fixture
import is more fragile than ten lines.
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    setup_test_component_platform,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

BLUEPRINT_PATH = "danspencer/flare.yaml"
SCHEDULE_SENSOR = "sensor.test_flare"

# What the schedule sensor publishes for every test in this layer, so a
# brightness assertion has one obvious expected value to name.
CURVE_BRIGHTNESS = 180
CURVE_KELVIN = 3000


@pytest.fixture
def hass_config_dir(tmp_path) -> str:
    (tmp_path / "custom_components").symlink_to(REPO_ROOT / "custom_components")
    (tmp_path / "blueprints").symlink_to(REPO_ROOT / "blueprints")
    return str(tmp_path)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def expected_lingering_timers():
    """Every test here sets up a real automation, which arms the
    blueprint's `adaptive_tick` time_pattern trigger (`update_interval`,
    every minute by default). That timer is still correctly scheduled
    when the test ends, because nothing tears the automation down first.

    Overrides pytest-homeassistant-custom-component's own default
    (False), which otherwise fails every test in this directory at
    teardown for that expected timer rather than for a real leak.
    tests/integration/test_blueprint.py carries the same override for
    the same reason.
    """
    return True


class FakeBulb(LightEntity):
    """A real LightEntity whose state genuinely changes when
    light.turn_on reaches it - the whole point of this layer.

    It is the ONLY fake here, and it stands in for the radio: HA's real
    light component registers it, real service dispatch and schema
    validation run against it, and hass.states reports what it actually
    holds rather than what someone asked for.

    Colour-temp only, because that is what the curve drives. A bulb
    needing RGB is a per-test concern, not a default.
    """

    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_should_poll = False

    def __init__(self, name: str) -> None:
        self._attr_name = name
        self._attr_unique_id = name
        self._attr_is_on = False
        self._attr_brightness = None
        self._attr_color_temp_kelvin = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()


def occupancy(hass: HomeAssistant, entity_id: str, state: str) -> None:
    """An occupancy sensor, as a plain state write.

    Not a real entity, and deliberately so - unlike the bulbs. A light
    is an OUTPUT whose state our code has to genuinely drive through
    real dispatch, which is the thing worth proving. An occupancy sensor
    is pure INPUT: nothing under test ever writes to it, and its entire
    contract with the blueprint is what hass.states reports.

    This is equivalent to a real sensor at the point of consumption, not
    merely close enough. The occupancy integration filters by
    device_class via helpers/entity.py's get_device_class, which reads
    the state machine FIRST and falls back to the entity registry only
    when no state exists - so a real BinarySensorEntity would add a
    platform whose only job is to put this same string in this same
    place. tests/integration/test_blueprint.py's own _occupancy helper
    does the same.
    """
    hass.states.async_set(entity_id, state, {"device_class": "occupancy"})


@pytest.fixture(autouse=True)
def schedule_sensor(hass: HomeAssistant) -> None:
    """The adaptive sensor every room automation follows.

    A plain state write for the same reason as occupancy above: the
    blueprint only ever reads its state and attributes. The real sensor
    entity is tests/integration/test_services.py's concern.
    """
    hass.states.async_set(
        SCHEDULE_SENSOR,
        "Evening",
        {"brightness": CURVE_BRIGHTNESS, "color_temp": CURVE_KELVIN},
    )


@pytest.fixture
async def flare(hass: HomeAssistant) -> MockConfigEntry:
    """The real tracking entry, so the real flare.* services register.

    async_forward_entry_setups is patched out for the duration of setup.
    It would set up the sensor and button COMPONENTS successfully and
    then fail to set up flare's own platforms, because resolving them
    pulls the manifest's frontend dependency and hass_frontend is not
    installed (this repo's whole integration suite avoids it - see
    tests/integration/test_services.py's _setup_entry). That leaves the
    components loaded with this entry never registered inside them, and
    teardown's unload then raises "Config entry was never loaded!".

    That combination is unique to this layer: test_services.py forwards
    but never sets up `automation`, and test_blueprint.py sets up
    `automation` but never calls async_setup_entry at all, so neither
    hits it. Nothing here needs the diagnostic sensor - a test that
    wants claims should attach the platform directly, the way
    test_services.py's _attach_tracking_sensors does.
    """
    from custom_components.flare import async_setup_entry
    from custom_components.flare.const import (
        CONF_ENTRY_TYPE,
        DOMAIN,
        ENTRY_TYPE_TRACKING,
    )

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def add_bulbs(hass: HomeAssistant):
    """Registers fake bulbs against HA's real light component.

    Call once per test - setup_test_component_platform registers the
    whole platform, so a second call in the same test is not additive.
    """

    async def _add(*names: str) -> list[FakeBulb]:
        bulbs = [FakeBulb(name) for name in names]
        setup_test_component_platform(hass, "light", bulbs)
        assert await async_setup_component(hass, "light", {"light": {"platform": "test"}})
        await hass.async_block_till_done()
        for bulb in bulbs:
            assert bulb.entity_id, f"{bulb.name} never got an entity_id"
        return bulbs

    return _add


@pytest.fixture
def setup_room(hass: HomeAssistant):
    """A real automation from the real blueprint, driving the given
    bulbs, with any blueprint input overridable by keyword.

    Inputs left unset take the blueprint's own defaults, so a test names
    only what it is actually about.
    """

    async def _setup(
        *,
        lights: list[FakeBulb | str],
        occupancy_sensors: list[str] | None = None,
        **inputs: Any,
    ) -> None:
        entity_ids = [
            light if isinstance(light, str) else light.entity_id for light in lights
        ]
        target = entity_ids + list(occupancy_sensors or [])
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": [
                    {
                        "alias": "room",
                        "use_blueprint": {
                            "path": BLUEPRINT_PATH,
                            "input": {
                                "adaptive_sensor": SCHEDULE_SENSOR,
                                "room_target": {"entity_id": target},
                                **inputs,
                            },
                        },
                    }
                ]
            },
        )
        await hass.async_block_till_done()
        # A blueprint that fails to generate leaves no automation at
        # all, and every assertion downstream would then read as a
        # behaviour result ("the light stayed off") rather than as the
        # setup failure it is.
        assert hass.states.get("automation.room") is not None, (
            "the automation failed to set up from the blueprint"
        )

    return _setup
