"""The behaviour layer's fake bulb and helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.util import color as color_util
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_ZONES,
    SUBENTRY_TYPE_FLARE,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_ZONE,
)
from tests.support import REPO_ROOT

SCHEDULE_SENSOR = "sensor.test_flare"
TRACE_DIR = REPO_ROOT / "trace-dumps"  # build output, see .gitignore

# The pinned day: sunset at 18:00 starts Evening, the clock starts at
# 19:00, in Evening's hold at the default curve values.
SUNSET = time(18, 0)
START = time(19, 0, 2)  # two seconds past the minute, clear of the tick
CURVE_BRIGHTNESS = 180
CURVE_KELVIN = 3200
NIGHT_BRIGHTNESS = 80
# The moment each phase begins on the pinned day.
PHASE_STARTS = {"Night": time(22, 0, 2)}

HALL_SENSOR = "binary_sensor.hall_occupancy"
# The `zone` fixture's zone, and the name of the area it's placed in.
ZONE = "behaviour_test_room"
# Several fittings, so they share one brightness group as a real room's do.
HALL_BULBS = ("hall_pendant", "hall_spot_1", "hall_spot_2", "hall_spot_3", "hall_spot_4", "hall_lamp")


class FakeBulb(LightEntity):
    """A real LightEntity whose state changes when light.turn_on reaches
    it - the only fake in this layer, standing in for the radio.

    Colour-temp only by default. Quirks, for test_device_quirks.py:
    supports_rgb; reports_via_rgb (translates Kelvin commands and reports
    rgb_color, like IKEA TRADFRI spots); needs_two_step (a call that
    changes brightness and sets a colour applies only the brightness);
    supports_transition (HA drops `transition` for a light without it);
    reports_off_late (switches off, but only reports it on
    async_report_off(), as a slow Zigbee bulb does).
    """

    _attr_should_poll = False

    def __init__(
        self,
        name: str,
        *,
        supports_rgb=False,
        reports_via_rgb=False,
        needs_two_step=False,
        supports_transition=False,
        reports_off_late=False,
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
        if supports_transition:
            self._attr_supported_features = LightEntityFeature.TRANSITION
        self._reports_off_late = reports_off_late
        self._attr_color_mode = ColorMode.COLOR_TEMP
        self._reports_via_rgb = reports_via_rgb
        # Gated on brightness *changing*: two-step's second call re-sends
        # the same brightness with the colour, and must land.
        self._needs_two_step = needs_two_step

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._attr_available = True
        has_colour = ATTR_COLOR_TEMP_KELVIN in kwargs or ATTR_RGB_COLOR in kwargs
        brightness_changing = ATTR_BRIGHTNESS in kwargs and kwargs[ATTR_BRIGHTNESS] != self._attr_brightness
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if self._needs_two_step and brightness_changing and has_colour:
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
        if self._reports_off_late:
            return
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_report_off(self) -> None:
        """The late report of a reports_off_late bulb's turn-off."""
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_go_unavailable(self) -> None:
        """A dropped Zigbee/MQTT connection."""
        self._attr_available = False
        self.async_write_ha_state()

    async def async_echo(self, *, is_on=True, brightness=None, color_temp_kelvin=None, rgb_color=None) -> None:
        """A state report of the device's own, under a fresh context (as on
        a reconnect or a retained MQTT message), rather than a response to
        a service call."""
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
    """An occupancy sensor. A plain state is exactly what the occupancy
    integration reads, so no real entity is needed."""
    hass.states.async_set(entity_id, state, {"device_class": "occupancy"})


def today_at(when: time) -> datetime:
    return dt_util.now().replace(hour=when.hour, minute=when.minute, second=when.second, microsecond=0)


async def move_to_phase(hass: HomeAssistant, frozen, phase: str) -> None:
    """Move the clock to the start of `phase` and let the schedule and the
    blueprint's tick run."""
    frozen.move_to(today_at(PHASE_STARTS[phase]))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()


def room_brightness(hass: HomeAssistant, bulbs) -> dict[str, object]:
    """Every bulb as {entity_id: brightness or 'off'}, so a failure names
    every fitting that was wrong."""
    result: dict[str, object] = {}
    for bulb in bulbs:
        state = hass.states.get(bulb.entity_id)
        result[bulb.entity_id] = state.attributes.get("brightness") if state.state == "on" else "off"
    return result


async def let_time_pass(hass: HomeAssistant, frozen, seconds: int) -> None:
    """Move now() AND fire the timers: async_fire_time_changed alone
    doesn't move now(), which the blueprint's Wait time check reads."""
    frozen.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def setup_schedule(hass: HomeAssistant) -> MockConfigEntry:
    """A real Schedules entry with one sensor, "Test" (sensor.test_flare)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}",
        version=3,
        subentries_data=[ConfigSubentryData(subentry_type=SUBENTRY_TYPE_SENSOR, title="Test", unique_id="test", data={})],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def setup_zones(hass: HomeAssistant, names: list[str], *, options: dict | None = None) -> dict[str, str]:
    """A real Zones entry with a zone per name, plus an area of each name
    for bulbs to sit in. Returns {name: area_id}."""
    areas = {name: ar.async_get(hass).async_get_or_create(name).id for name in names}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES},
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_ZONES}",
        version=3,
        options=options or {},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_ZONE, title=name, unique_id=name, data={}
            )
            for name, area_id in areas.items()
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return areas


async def flares_entry(hass: HomeAssistant) -> MockConfigEntry:
    """The Flares entry, created and set up if there isn't one yet."""
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES]
    if entries:
        return entries[0]
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_FLARES}, unique_id=f"{DOMAIN}_{ENTRY_TYPE_FLARES}", version=3
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def add_room_flares(hass: HomeAssistant, automations: list[str] | None = None) -> dict:
    """Runs Add flare's "Rooms from the FLARE blueprint" step, picking
    `automations` (every room offered, if None). Returns the flow's result."""
    entry = await flares_entry(hass)
    flows = hass.config_entries.subentries
    result = await flows.async_init((entry.entry_id, SUBENTRY_TYPE_FLARE), context={"source": "user"})
    result = await flows.async_configure(result["flow_id"], {"next_step_id": "blueprint"})
    if result["type"] != "form":
        return result
    offered = _default(result, "automation")
    result = await flows.async_configure(
        result["flow_id"], {"automation": offered if automations is None else automations}
    )
    await hass.async_block_till_done()
    return result


async def add_flare(hass: HomeAssistant, automation: str = "automation.room", *, name: str = "Room") -> str:
    """A flare over one blueprint room, added through the real flow and then
    renamed. Returns its entity_id."""
    result = await add_room_flares(hass, [automation])
    assert result["reason"] == "flares_added", result
    entry = await flares_entry(hass)
    (subentry_id,) = [i for i, s in entry.subentries.items() if s.title == hass.states.get(automation).name]
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_FLARE), context={"source": "reconfigure", "subentry_id": subentry_id}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": name, "lights_input": "room_target"}
    )
    assert result["reason"] == "reconfigure_successful", result
    await hass.async_block_till_done()
    return f"light.{name.lower()}_flare"


def _default(result, key: str):
    """A form field's default, as the frontend would pre-fill it."""
    for field in result["data_schema"].schema:
        if str(field) == key:
            return field.default()
    return None


def schedule_device(hass: HomeAssistant) -> str:
    """The device of the "Test" schedule, which the blueprint's Schedule input
    takes."""
    (entry,) = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SCHEDULES]
    (subentry_id,) = [i for i, s in entry.subentries.items() if s.title == "Test"]
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, subentry_id), entry.entry_id)
    assert device is not None, "the Test schedule has no device"
    return device.id


def zone_device(hass: HomeAssistant, name: str) -> str:
    """The device of the zone called `name`, which the blueprint's Zone input
    takes."""
    (entry,) = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ZONES]
    (subentry_id,) = [i for i, s in entry.subentries.items() if s.title == name]
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, subentry_id), entry.entry_id)
    assert device is not None, f"zone {name} has no device"
    return device.id


async def at(hass: HomeAssistant, frozen, hour: int, minute: int, second: float) -> None:
    """Move the clock to a moment today and fire whatever's due by then."""
    frozen.move_to(dt_util.now().replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(seconds=second))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


def dump_traces(hass: HomeAssistant, directory: Path, *, test_id: str, outcome: str, filename: str | None = None) -> Path | None:
    """Write every automation trace hass holds to `directory`. Returns the
    path, or None if there was nothing to write."""
    from homeassistant.components.trace.const import DATA_TRACE
    # HA's own trace encoder: `for:` puts a timedelta in the variables.
    from homeassistant.helpers.json import ExtendedJSONEncoder

    traces = hass.data.get(DATA_TRACE) or {}
    captured = [trace.as_extended_dict() for bucket in traces.values() for trace in bucket.all_traces()]
    if not captured:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', filename or test_id)}.json"
    path.write_text(json.dumps({"test": test_id, "outcome": outcome, "traces": captured}, cls=ExtendedJSONEncoder, indent=2))
    return path
