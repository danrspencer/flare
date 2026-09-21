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

import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import color as color_util
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    setup_test_component_platform,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

BLUEPRINT_PATH = "danspencer/flare.yaml"
SCHEDULE_SENSOR = "sensor.test_flare"

# Where captured automation traces land. Build output, never committed -
# see .gitignore. CI uploads the directory as an artifact and renders
# the traces into the job summary.
TRACE_DIR = REPO_ROOT / "trace-dumps"

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
def frozen_time():
    """Wall-clock control for every test here.

    Each test sets up a real automation carrying a live `tick`
    (time_pattern, every minute), so a test whose setup-and-assert
    window straddles a real minute boundary can have one fire for real
    mid-test - indistinguishable from the thing being asserted.

    `real_asyncio=True` is not optional and not cosmetic: without it
    freezegun also mocks `time.monotonic`, which is the clock asyncio
    uses to schedule every pending timer, and a live loop does not
    tolerate that - it hangs, or fires timers wildly out of order. See
    tests/integration/test_blueprint.py's own frozen_time for the full
    account; this is deliberately the same shape.

    Anchoring a couple of seconds PAST the minute (rather than at
    utcnow() verbatim, which could land arbitrarily close to a boundary)
    leaves ~58 real seconds before `tick` could next fire -
    longer than this whole directory takes to run.

    A test needing time to pass takes this fixture by name and calls
    `.tick()` on it. Never open a nested freeze_time.
    """
    anchor = dt_util.utcnow().replace(second=2, microsecond=0)
    with freeze_time(anchor, real_asyncio=True) as frozen:
        yield frozen


async def let_time_pass(hass: HomeAssistant, frozen, seconds: int) -> None:
    """Advance the clock AND fire the timers that should have run.

    Two separate things, which is the trap: `async_fire_time_changed`
    fires the event a time_pattern trigger waits on but does NOT move
    `now()`, so any template comparing `now() - last_changed` (the
    blueprint's own wait-time check does exactly that) still sees no
    elapsed time. Ticking the freeze moves `now()` but schedules
    nothing. Both are needed.
    """
    frozen.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def expected_lingering_timers():
    """Every test here sets up a real automation, which arms the
    blueprint's `tick` time_pattern trigger (`update_interval`,
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

    Colour-temp only by default, because that is what the curve drives.
    `supports_rgb`/`reports_via_rgb`/`needs_two_step` opt a specific bulb
    into the device quirks tests/behaviour/test_device_quirks.py needs;
    most tests want none of them.
    """

    _attr_should_poll = False

    def __init__(
        self,
        name: str,
        *,
        supports_rgb: bool = False,
        reports_via_rgb: bool = False,
        needs_two_step: bool = False,
    ) -> None:
        self._attr_name = name
        self._attr_unique_id = name
        self._attr_is_on = False
        self._attr_available = True
        self._attr_brightness = None
        self._attr_color_temp_kelvin = None
        self._attr_rgb_color = None
        modes = {ColorMode.COLOR_TEMP}
        if supports_rgb or reports_via_rgb:
            modes.add(ColorMode.RGB)
        self._attr_supported_color_modes = modes
        self._attr_color_mode = ColorMode.COLOR_TEMP
        # Some real bulbs (the IKEA TRADFRI incident this stands in for)
        # only ever report their actual colour via rgb_color, translating
        # any color_temp_kelvin command internally rather than echoing it
        # back the way a plain colour-temp bulb does.
        self._reports_via_rgb = reports_via_rgb
        # The actual defect two-step transitions exist for
        # (docs/advanced/reference.md: "sent together, they snap or drop
        # one of the two"): brightness genuinely CHANGING VALUE in the
        # same call as a colour change only ever applies the brightness.
        # Real two-step dispatch's own second call (services/handlers.py's
        # _two_step_turn_on) still carries brightness alongside colour -
        # it just re-sends the SAME brightness the first call already
        # landed, which is why "brightness changing" rather than merely
        # "brightness present" is what has to gate this: a bulb that
        # dropped colour whenever both keys were merely PRESENT would
        # also drop it on that legitimate second call, indistinguishable
        # from a broken combined dispatch.
        self._needs_two_step = needs_two_step

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._attr_available = True
        has_colour = ATTR_COLOR_TEMP_KELVIN in kwargs or ATTR_RGB_COLOR in kwargs
        brightness_changing = ATTR_BRIGHTNESS in kwargs and kwargs[ATTR_BRIGHTNESS] != self._attr_brightness
        drop_colour = self._needs_two_step and brightness_changing and has_colour
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if drop_colour:
            self.async_write_ha_state()
            return
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            if self._reports_via_rgb:
                self._attr_color_mode = ColorMode.RGB
                self._attr_rgb_color = color_util.color_temperature_to_rgb(kelvin)
                self._attr_color_temp_kelvin = None
            else:
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self._attr_color_temp_kelvin = kelvin
                self._attr_rgb_color = None
        if ATTR_RGB_COLOR in kwargs:
            self._attr_color_mode = ColorMode.RGB
            self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]
            self._attr_color_temp_kelvin = None
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_go_unavailable(self) -> None:
        """Stand in for a dropped Zigbee/MQTT connection."""
        self._attr_available = False
        self.async_write_ha_state()

    async def async_echo(
        self,
        *,
        is_on: bool = True,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        rgb_color: tuple | None = None,
    ) -> None:
        """A state report that did NOT arrive as this call's own
        response to a service call - standing in for the device's own
        asynchronous echo (a Zigbee/MQTT integration publishing on its
        own), which is what leaves an entity reporting under a context
        unrelated to whichever automation run last wrote it. Real bulbs
        do this constantly (reconnecting after a dropout, retained MQTT
        state); async_turn_on can't model it, because HA attaches the
        calling service's own context automatically.

        async_set_context is the same public hook HA's own entity
        component calls before invoking a service - using it here is
        not a hack around the framework, it is the framework's own way
        of saying "this write did not come from that context".
        """
        self.async_set_context(Context())
        self._attr_available = True
        self._attr_is_on = is_on
        if brightness is not None:
            self._attr_brightness = brightness
        if color_temp_kelvin is not None:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = color_temp_kelvin
            self._attr_rgb_color = None
        if rgb_color is not None:
            self._attr_color_mode = ColorMode.RGB
            self._attr_rgb_color = rgb_color
            self._attr_color_temp_kelvin = None
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


def set_phase(
    hass: HomeAssistant,
    phase: str,
    *,
    brightness: int = CURVE_BRIGHTNESS,
    kelvin: int = CURVE_KELVIN,
) -> None:
    """Repaint the schedule sensor, as the coordinator would.

    The blueprint's `adaptive` trigger filters `to:` the four phase
    names, so moving between them is what a real phase change looks
    like. Changing only the attributes fires nothing.
    """
    hass.states.async_set(
        SCHEDULE_SENSOR, phase, {"brightness": brightness, "color_temp": kelvin}
    )


def room_brightness(hass: HomeAssistant, bulbs) -> dict[str, object]:
    """Every bulb as {entity_id: brightness or 'off'}.

    Asserting on the whole room at once means a failure names which
    fittings were wrong rather than stopping at the first - "two spots
    missed it" is a different bug from "the room didn't light".
    """
    result: dict[str, object] = {}
    for bulb in bulbs:
        state = hass.states.get(bulb.entity_id)
        result[bulb.entity_id] = (
            state.attributes.get("brightness") if state.state == "on" else "off"
        )
    return result


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


async def _setup_tracking_entry(hass: HomeAssistant, *, tracked: bool) -> tuple[MockConfigEntry, str | None]:
    """The real Tracking config entry, so the real flare.* services
    register - optionally with a real state-device scope over one area,
    "behaviour_test_room".

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
    hits it.

    A device_id a caller passes as tracking_device_id must belong to
    THIS SAME entry's own subentries (write_tracking.py's
    resolve_scope_device checks `self._entry.subentries`, not the
    device registry at large) - so unlike
    tests/integration/test_blueprint.py's own _register_tracking_scope
    (fine there, because that suite mocks flare.apply_lighting and so
    never reaches real validation), a scope built for a REAL service
    call has to be a subentry of the exact entry these services were
    registered against. That's also why this can't be two separate
    config entries: flare.* services are hass-global, so a test wanting
    a real scope has to build it into the one Tracking entry that
    registers them, not alongside it.

    Returns (entry, area_id) - area_id is None for the untracked half.
    """
    from custom_components.flare import async_setup_entry
    from custom_components.flare.const import (
        CONF_ENTRY_TYPE,
        CONF_TARGET,
        DOMAIN,
        ENTRY_TYPE_TRACKING,
        SUBENTRY_TYPE_STATE,
    )
    from homeassistant.config_entries import ConfigSubentryData

    area_id = ar.async_get(hass).async_get_or_create("behaviour_test_room").id if tracked else None
    subentries_data = (
        [
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_STATE,
                title="behaviour_test_room",
                unique_id="behaviour_test_room",
                data={CONF_TARGET: {"area_id": [area_id]}},
            )
        ]
        if tracked
        else []
    )

    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING}, subentries_data=subentries_data
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await async_setup_entry(hass, entry)
    await hass.async_block_till_done()

    if tracked:
        await _attach_tracking_sensor(hass, entry, area_id)

    return entry, area_id


async def _attach_tracking_sensor(hass: HomeAssistant, entry: MockConfigEntry, area_id: str) -> None:
    r"""Creates the one state device's real tracking entity and a
    matching device, so claims have somewhere to live and
    resolve_scope_device has a device to resolve.

    Same shape as tests/integration/test_services.py's own
    _attach_tracking_sensors: async_forward_entry_setups is patched out
    for the whole entry above, so nothing else creates either. The real
    sensor platform is invoked directly with a capturing
    async_add_entities, exercising the real _StateTrackingSensor and the
    real registry routing; only HA's state publication is stubbed out.

    That stub is also why both the DEVICE and the sensor ENTITY need
    hand-built registry entries here, unlike test_services.py's own
    version (which relies on neither): that suite reads a scope's
    tracking_device_id straight off the device registry, but the
    blueprint has no device_id to start from - it has to find the scope
    itself, via tracking_scope_device_id's own Jinja: search this room's
    AREA for an entity matching `^sensor\..*_flare_tracking$`, the same
    path a real room with no explicit Area Target takes. `area_entities`
    reads the entity registry, not hass.states, so without a real
    registry entry (entity_id, device_id, and - since sensor.py's
    _assign_scope_area only runs from
    _StateTrackingSensor.async_added_to_hass, which a plain list-append
    add_entities never calls - area_id set by hand too) the search finds
    nothing and silently falls back to untracked. Caught by a throwaway
    probe test asserting a claim actually lands in
    registry.records_for_scope after a real run; every test in this file
    up to that point still passed, because none of them assert anything
    about tracking itself.
    """
    from custom_components.flare.const import DOMAIN
    from custom_components.flare.tracking.scope import state_instances
    from custom_components.flare.sensor import async_setup_entry as sensor_setup
    from custom_components.flare.tracking.write_tracking import ClaimRegistry

    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    registry = next(v for v in hass.data[DOMAIN].values() if isinstance(v, ClaimRegistry))
    for instance, entity in zip(state_instances(entry), [e for e in added if hasattr(e, "claims")]):
        entity.async_claims_changed = lambda: None
        registry.register(instance.subentry_id, entity)
        # The stub async_add_entities above is a plain list-append, not
        # the real entity platform - it never triggers the device
        # registration a real add_entities call does for an entity
        # carrying device_info. resolve_scope_device needs a real device
        # to resolve, so create it explicitly, the same identifiers
        # StateInstance.device_info would produce.
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers=instance.device_info["identifiers"], name=instance.title
        )
        dr.async_get(hass).async_update_device(device.id, area_id=area_id)
        er.async_get(hass).async_get_or_create(
            "sensor",
            DOMAIN,
            entity.unique_id,
            suggested_object_id=f"{instance.prefix}flare_tracking",
            device_id=device.id,
        )
        hass.states.async_set(entity.entity_id, "0")


@pytest.fixture(params=[False, True], ids=["untracked", "tracked"])
async def tracking_scope(request, hass: HomeAssistant) -> str | None:
    """The real Tracking entry (so flare.* services register), and
    whether the room's lights sit inside a real FLARE Tracking scope.

    Use this INSTEAD OF the plain `flare` fixture, never alongside it -
    both load a Tracking config entry, and flare.* services are
    hass-global, so a test can only sensibly have one such entry loaded
    (see _setup_tracking_entry).

    Parametrized so an ordinary behaviour test runs twice: once exactly
    as every behaviour test ran before this fixture existed (no state
    device at all - the blueprint's tracking_scope_device_id resolves to
    none, and apply_lighting is called with tracking_device_id: null,
    "write but track nothing" - see the NOT COVERED note at the bottom
    of test_core_capabilities.py), and once with a real FLARE Tracking
    scope claiming every light in the room. A capability whose outcome
    should not depend on tracking existing gets that proven for free,
    for no extra lines in the test itself.

    A test that is specifically ABOUT tracking - override protection,
    say - should depend on `tracked_scope` below instead: it always
    builds the scope, so such a test runs once, not twice. There is no
    meaningful "untracked" variant of a test whose whole point is
    tracking.

    Returns the AREA id, never the device id, because that is what
    add_bulbs(..., area_id=...) needs: the blueprint never names an area
    directly in these tests' room_target, so tracking_scope_device_id
    falls back to resolved_entities' own area - the same path a real
    room with no explicit Area Target takes (see the blueprint's own
    comment above that variable). None means the untracked half, and
    add_bulbs treats None as "assign no area at all".
    """
    _entry, area_id = await _setup_tracking_entry(hass, tracked=request.param)
    return area_id


@pytest.fixture
async def tracked_scope(hass: HomeAssistant) -> str:
    """Always builds a real FLARE Tracking scope. Use instead of `flare`
    (see tracking_scope's docstring for why) for a test that is itself
    about tracking rather than one of the ordinary capabilities
    `tracking_scope` parametrizes both sides of - such a test has no
    meaningful untracked half, so this runs it once, not twice.
    """
    _entry, area_id = await _setup_tracking_entry(hass, tracked=True)
    assert area_id is not None
    return area_id


@pytest.fixture
async def flare(hass: HomeAssistant) -> MockConfigEntry:
    """The real tracking entry, so the real flare.* services register -
    with no state-device scope over anything. A test that wants claims
    should depend on `tracking_scope` or `tracked_scope` instead, not on
    this fixture as well.
    """
    entry, _area_id = await _setup_tracking_entry(hass, tracked=False)
    return entry


@pytest.fixture(autouse=True)
def capture_trace(request, hass: HomeAssistant):
    """Write the blueprint's real automation trace to TRACE_DIR.

    HA's trace machinery is already running in these tests - setting up
    the real `automation` component is all it takes - so every blueprint
    run here is traced exactly as it would be on a live instance, and
    without this we simply threw that away. The trace carries what you
    actually read a trace for: which conditions passed or failed, which
    `choose:` branch was taken, and the resolved value of every variable
    at each step (`changed_variables`), keyed by HA's own step paths
    (e.g. `action/0/default/1/then/1/if/condition/0`).

    It cannot be loaded into HA's own trace viewer, which is worth
    knowing before anyone tries: the websocket API is read-only
    (trace/get, trace/list, trace/contexts - no import), and the trace
    store is written only on EVENT_HOMEASSISTANT_STOP and never read
    back at startup. So the JSON here is for our own renderer, not for
    HA.

    Depends on `hass` deliberately: that makes this fixture tear down
    BEFORE hass does, so the trace data is still live when it is read.
    Reading it after hass teardown gets nothing.
    """
    yield

    dump_traces(
        hass,
        TRACE_DIR,
        test_id=request.node.nodeid,
        outcome="failed" if getattr(request.node, "behaviour_failed", False) else "passed",
        filename=request.node.name,
    )


def dump_traces(
    hass: HomeAssistant,
    directory: Path,
    *,
    test_id: str,
    outcome: str,
    filename: str | None = None,
) -> Path | None:
    """Write every trace hass currently holds to `directory`.

    Split out of capture_trace so the write half is testable on its own.
    A fixture writes at teardown, so a test can never see its own file -
    without this, the only way to check the capture works is to assert
    on a file some OTHER test left behind, which makes the test
    order-dependent and have it fail in isolation for reasons unrelated
    to the capture (tried; it did exactly that).

    Returns the path written, or None when there was nothing to write.
    """
    from homeassistant.components.trace.const import DATA_TRACE
    # ExtendedJSONEncoder, not JSONEncoder - the same encoder HA's own
    # trace store uses. A trigger carrying `for:` (motion_off does)
    # puts a timedelta in changed_variables, which plain JSONEncoder
    # cannot serialise: the capture then raises at teardown and every
    # test in the run errors. ExtendedJSONEncoder encodes a timedelta
    # as total_seconds and falls back to repr() for anything else, so
    # an unexpected object can never take the suite down again.
    from homeassistant.helpers.json import ExtendedJSONEncoder as JSONEncoder

    traces = hass.data.get(DATA_TRACE) or {}
    captured = [
        trace.as_extended_dict()
        for bucket in traces.values()
        for trace in bucket.all_traces()
    ]
    if not captured:
        return None

    directory.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", filename or test_id)
    path = directory / f"{safe}.json"
    payload = {"test": test_id, "outcome": outcome, "traces": captured}
    path.write_text(json.dumps(payload, cls=JSONEncoder, indent=2))
    return path


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Tag the test item with its outcome so capture_trace can record it.

    A fixture cannot otherwise see whether the test that just ran
    passed, and a trace is most worth reading when it failed.
    """
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        item.behaviour_failed = True


@pytest.fixture
def add_bulbs(hass: HomeAssistant):
    """Registers fake bulbs against HA's real light component.

    Call once per test - setup_test_component_platform registers the
    whole platform, so a second call in the same test is not additive.

    `area_id`, when given, is applied to every bulb's own entity
    registry entry afterwards - the same shape sensor.py's
    _assign_scope_area produces for a real light, and what a room needs
    for the blueprint's tracking_scope_device_id fallback to find a
    scope. Pass tracking_scope or tracked_scope's return value; leave it
    unset for a room with no area at all, which is what every call here
    did before those fixtures existed.

    `overrides` maps a bulb's name to a dict of per-bulb settings:
    anything else is passed straight through to FakeBulb's own
    constructor (`supports_rgb`/`reports_via_rgb`), and a `device` key
    ({"manufacturer": ..., "model": ...}) registers a real device for
    that bulb and links its entity to it - what
    EntityLookup.manufacturer_model() (and so two-step pattern
    matching) actually reads. Registering it here rather than via
    FakeBulb's own device_info is deliberate: this platform is set up
    from YAML (setup_test_component_platform + a plain `platform: test`
    entry), which has no config_entry, and HA's entity platform only
    creates a device from device_info when one exists (see
    homeassistant/helpers/entity_platform.py's _async_add_entity) - so
    a YAML-registered entity's device_info is silently never acted on.
    """

    async def _add(
        *names: str, area_id: str | None = None, **overrides: dict
    ) -> list[FakeBulb]:
        bulbs = [
            FakeBulb(name, **{k: v for k, v in overrides.get(name, {}).items() if k != "device"})
            for name in names
        ]
        setup_test_component_platform(hass, "light", bulbs)
        assert await async_setup_component(hass, "light", {"light": {"platform": "test"}})
        await hass.async_block_till_done()
        for bulb in bulbs:
            assert bulb.entity_id, f"{bulb.name} never got an entity_id"
        if area_id is not None:
            registry = er.async_get(hass)
            for bulb in bulbs:
                registry.async_update_entity(bulb.entity_id, area_id=area_id)
        owner = None
        for bulb in bulbs:
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
            er.async_get(hass).async_update_entity(bulb.entity_id, device_id=device_entry.id)
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
                        # A stable id keys the trace as automation.room
                        # rather than automation.None - without it every
                        # automation collides on one key and the dump is
                        # unreadable.
                        "id": "room",
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
