"""The behaviour layer's fake bulb and helpers."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntryState, ConfigSubentryData
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import color as color_util
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.flare import async_setup_entry
from custom_components.flare.const import CONF_ENTRY_TYPE, CONF_TARGET, DOMAIN, ENTRY_TYPE_TRACKING, SUBENTRY_TYPE_STATE
from custom_components.flare.sensor import async_setup_entry as sensor_setup
from custom_components.flare.tracking.scope import state_instances
from custom_components.flare.tracking.write_tracking import ClaimRegistry
from tests.support import REPO_ROOT

SCHEDULE_SENSOR = "sensor.test_flare"
TRACE_DIR = REPO_ROOT / "trace-dumps"  # build output, see .gitignore
# What the schedule sensor publishes throughout.
CURVE_BRIGHTNESS = 180
CURVE_KELVIN = 3000

HALL_SENSOR = "binary_sensor.hall_occupancy"
# Several fittings, so they share one multiplier bucket as a real room's do.
HALL_BULBS = ("hall_pendant", "hall_spot_1", "hall_spot_2", "hall_spot_3", "hall_spot_4", "hall_lamp")


class FakeBulb(LightEntity):
    """A real LightEntity whose state changes when light.turn_on reaches
    it - the only fake in this layer, standing in for the radio.

    Colour-temp only by default. Quirks, for test_device_quirks.py:
    supports_rgb; reports_via_rgb (translates Kelvin commands and reports
    rgb_color, like IKEA TRADFRI spots); needs_two_step (a call that
    changes brightness and sets a colour applies only the brightness).
    """

    _attr_should_poll = False

    def __init__(self, name: str, *, supports_rgb=False, reports_via_rgb=False, needs_two_step=False) -> None:
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


def set_phase(hass: HomeAssistant, phase: str, *, brightness: int = CURVE_BRIGHTNESS, kelvin: int = CURVE_KELVIN) -> None:
    """Repaint the schedule sensor, as the coordinator would."""
    hass.states.async_set(SCHEDULE_SENSOR, phase, {"brightness": brightness, "color_temp": kelvin})


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


async def setup_tracking_entry(hass: HomeAssistant, *, tracked: bool) -> tuple[MockConfigEntry, str | None]:
    """The real Tracking entry, so the real services register, optionally
    with one scope over the area "behaviour_test_room". Returns (entry,
    area_id); area_id is None when untracked.

    Platform forwarding is patched out: it would load the frontend package.
    A scope a real service call names has to be a subentry of this same
    entry, since the services validate against it."""
    area_id = ar.async_get(hass).async_get_or_create("behaviour_test_room").id if tracked else None
    subentries = [
        ConfigSubentryData(
            subentry_type=SUBENTRY_TYPE_STATE,
            title="behaviour_test_room",
            unique_id="behaviour_test_room",
            data={CONF_TARGET: {"area_id": [area_id]}},
        )
    ] if tracked else []
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING}, subentries_data=subentries)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    if tracked:
        await _attach_tracking_sensor(hass, entry, area_id)
    return entry, area_id


async def _attach_tracking_sensor(hass: HomeAssistant, entry: MockConfigEntry, area_id: str) -> None:
    r"""The scope's real tracking entity, attached with a capturing
    add_entities. The blueprint finds a scope by searching the room's
    area for `sensor.*_flare_tracking` in the entity registry, so the
    device, the entity and its area are all registered by hand here."""
    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    registry = next(v for v in hass.data[DOMAIN].values() if isinstance(v, ClaimRegistry))
    for instance, entity in zip(state_instances(entry), [e for e in added if hasattr(e, "claims")]):
        entity.async_claims_changed = lambda: None
        registry.register(instance.subentry_id, entity)
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers=instance.device_info["identifiers"], name=instance.title
        )
        dr.async_get(hass).async_update_device(device.id, area_id=area_id)
        er.async_get(hass).async_get_or_create(
            "sensor", DOMAIN, entity.unique_id, suggested_object_id=f"{instance.prefix}flare_tracking", device_id=device.id
        )
        hass.states.async_set(entity.entity_id, "0")


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
