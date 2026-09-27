"""
Schedule coordinator: one per schedule instance (see ScheduleInstance
below), created in __init__.py and stored in hass.data, shared by that
schedule's sensor (sensor.py), phase-override select (select.py) and
config entities (number.py, time.py, switch.py).

Boundaries: morning/day/night are today's configured time-of-day;
evening is sunset (sun.sun's next_setting), clamped between the
earliest/latest bounds. The times and the curve values are read live off
this instance's own time.*/number.* entities on every update, not from
config-entry data - see time.py/number.py.

Override: select.<prefix>flare_phase can pin the phase used for "right
now"; _phase_override() reads its live state on every update. The
override deliberately affects only the "right now" phase/brightness/
kelvin, NOT the full-day curve (`points`): pinning the present to
Evening doesn't change what the schedule looks like at 9am.

Every schedule is a "sensor" subentry of the Schedules entry (added via
config_flow.py's SensorSubentryFlow), with a prefixed entity_id
(sensor.living_room_flare) and its own device. schedule_instances() is
the one place that enumerates them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify
import homeassistant.util.dt as dt_util

from ..const import DOMAIN, SUBENTRY_TYPE_SENSOR
from .curve import DEFAULT_SCHEDULE_HOURS, phase_at, targets_for_phase

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=60)

# The five schedule-time entities every instance gets (time.py) - also
# each one's entity_id suffix (time.<prefix><key>).
TIME_KEYS = (
    "morning_time",
    "day_time",
    "evening_earliest_time",
    "evening_latest_time",
    "night_time",
)

# The curve number entities every instance gets (number.py): a
# brightness and Kelvin per phase, then a transition length for each -
# also each one's entity_id suffix (number.<prefix><key>). Unset
# (entity unavailable, e.g. mid-startup before platforms have loaded),
# curve.py's DEFAULT_CURVE_VALUES apply. This order also drives the
# compute_curve service schema.
CURVE_KEYS = (
    "morning_brightness",
    "morning_kelvin",
    "day_brightness",
    "day_kelvin",
    "evening_brightness",
    "evening_kelvin",
    "night_brightness",
    "night_kelvin",
    "morning_brightness_transition",
    "morning_kelvin_transition",
    "day_brightness_transition",
    "day_kelvin_transition",
    "evening_brightness_transition",
    "evening_kelvin_transition",
    "night_brightness_transition",
    "night_kelvin_transition",
)


@dataclass
class ScheduleInstance:
    """One sensor's schedule/curve setup, derived from a "sensor"
    subentry. Always named, always gets its own device - see
    device_info below."""

    subentry_id: str  # hass.data storage key; also passed to async_add_entities(config_subentry_id=...)
    # "<slug>_" - entity_id prefix, derived from the (required) name. Empty
    # if the name slugifies to nothing, giving an unprefixed entity_id
    # rather than a broken "sensor._foo".
    prefix: str
    override_entity_id: str  # select.<prefix>flare_phase
    sticky_entity_id: str  # switch.<prefix>sticky_phase_override
    title: str  # the subentry's name (required - see SensorSubentryFlow)

    @property
    def device_info(self) -> DeviceInfo:
        """Every instance gets its own device, named what the user
        typed. With has_entity_name=True on every entity, HA prefixes
        each entity's short name with the device's, so renaming the
        device renames them all."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.subentry_id)},
            name=self.title or "Adaptive Lighting",
            entry_type=DeviceEntryType.SERVICE,
        )

    def time_entity_id(self, key: str) -> str:
        return f"time.{self.prefix}{key}"

    def number_entity_id(self, key: str) -> str:
        return f"number.{self.prefix}{key}"


def schedule_instances(entry: ConfigEntry) -> list[ScheduleInstance]:
    """Every schedule instance this entry should set up sensors/select/
    config entities for - one per "sensor" subentry (see config_flow.py's
    SensorSubentryFlow). The entry itself never carries a schedule -
    the services belong to the Tracking entry (see services/handlers.py)."""
    instances = []
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_SENSOR:
            continue
        slug = slugify(subentry.title)
        prefix = f"{slug}_" if slug else ""
        instances.append(
            ScheduleInstance(
                subentry_id=subentry_id,
                prefix=prefix,
                override_entity_id=f"select.{prefix}flare_phase",
                sticky_entity_id=f"switch.{prefix}sticky_phase_override",
                title=subentry.title,
            )
        )
    return instances


def _curve_kwargs(hass: HomeAssistant, instance: ScheduleInstance) -> dict[str, int]:
    kwargs: dict[str, int] = {}
    for key in CURVE_KEYS:
        state = hass.states.get(instance.number_entity_id(key))
        if state is None or state.state in ("unknown", "unavailable"):
            continue
        try:
            kwargs[key] = round(float(state.state))
        except (TypeError, ValueError):
            continue
    return kwargs


def _time_str_to_today_timestamp(time_str: str | None) -> float | None:
    """A time.py entity's state ("HH:MM:SS", TimeEntity's own string
    format) -> today's timestamp for that time-of-day, in the local
    timezone."""
    if not time_str:
        return None
    t = dt_util.parse_time(time_str)
    if t is None:
        return None
    now_local = dt_util.now()
    return now_local.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0).timestamp()


def _time_ts(hass: HomeAssistant, instance: ScheduleInstance, key: str) -> float:
    """Today's timestamp for one boundary time entity, never None.

    Falls back to the entity's own default (time.py's _DEFAULTS) whenever
    a real value can't be read - either the entity doesn't exist yet
    (the coordinator's very first refresh runs before platforms are
    forwarded, see __init__.py's async_setup_entry) or it exists but has
    no value ("unknown"/"unavailable"). The second case happens on every
    reload: unloading an entry leaves its entities in the state machine
    as "unavailable". Returning None would crash phase_at() and wedge
    setup permanently, since every retry sees the same states. The real
    value lands once the platform loads, and async_setup_entry refreshes
    again after forwarding platforms to pick it up."""
    state = hass.states.get(instance.time_entity_id(key))
    # parse_time("unknown"/"unavailable") is None, so both no-entity and
    # no-value roads lead through the same default fallback.
    ts = _time_str_to_today_timestamp(state.state) if state is not None else None
    if ts is None:
        default_hour = DEFAULT_SCHEDULE_HOURS[key[: -len("_time")]]
        ts = _time_str_to_today_timestamp(f"{default_hour:02d}:00:00")
    return ts


def _compute_boundaries(hass: HomeAssistant, instance: ScheduleInstance) -> dict[str, float]:
    morning_ts = _time_ts(hass, instance, "morning_time")
    day_ts = _time_ts(hass, instance, "day_time")
    night_ts = _time_ts(hass, instance, "night_time")
    earliest_ts = _time_ts(hass, instance, "evening_earliest_time")
    latest_ts = _time_ts(hass, instance, "evening_latest_time")

    sun_state = hass.states.get("sun.sun")
    next_setting = sun_state.attributes.get("next_setting") if sun_state else None
    sunset_dt = dt_util.parse_datetime(next_setting) if next_setting else None
    if sunset_dt is not None:
        # next_setting is exactly that - "next" - so once today's sunset
        # has passed it points at tomorrow's, a full day ahead of today's
        # schedule. Naively clamping that against today's earliest/latest
        # bounds always lands on latest, which yanks the Evening boundary
        # later *after* Evening has already started (phase flips back to
        # Day until the latest bound). Project the sunset's time-of-day
        # onto today instead - tomorrow's sunset time differs from
        # today's by at most a couple of minutes, well inside the
        # earliest/latest clamp's tolerance for caring.
        sunset_local = dt_util.as_local(sunset_dt)
        sunset_ts = (
            dt_util.now()
            .replace(hour=sunset_local.hour, minute=sunset_local.minute, second=sunset_local.second, microsecond=0)
            .timestamp()
        )
    else:
        sunset_ts = latest_ts

    evening_ts = max(earliest_ts, min(sunset_ts, latest_ts))

    return {
        "morning_ts": morning_ts,
        "day_ts": day_ts,
        "evening_ts": evening_ts,
        "night_ts": night_ts,
        "evening_earliest_ts": earliest_ts,
        "evening_latest_ts": latest_ts,
    }


def _compute_curve_points(boundaries: dict[str, float], curve_kwargs: dict[str, int]) -> list[dict[str, Any]]:
    morning_ts, day_ts, evening_ts, night_ts = (
        boundaries["morning_ts"],
        boundaries["day_ts"],
        boundaries["evening_ts"],
        boundaries["night_ts"],
    )
    midnight = dt_util.start_of_local_day().timestamp()
    points = []
    for i in range(289):
        t = midnight + i * 300
        phase = phase_at(t, morning_ts, day_ts, evening_ts, night_ts)
        targets = targets_for_phase(phase, t, evening_ts, day_ts, night_ts, morning_ts, **curve_kwargs)
        points.append(
            {
                "t": int(t),
                "brightness": targets["brightness"],
                "kelvin": targets["kelvin"],
            }
        )
    return points


def _phase_override(hass: HomeAssistant, override_entity_id: str) -> str | None:
    state = hass.states.get(override_entity_id)
    if state is None or state.state in ("Auto", "unknown", "unavailable"):
        return None
    return state.state


class ScheduleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, instance: ScheduleInstance) -> None:
        super().__init__(hass, _LOGGER, name=f"Adaptive Lighting schedule ({instance.title})", update_interval=UPDATE_INTERVAL)
        self._instance = instance

    async def _async_update_data(self) -> dict[str, Any]:
        boundaries = _compute_boundaries(self.hass, self._instance)
        curve_kwargs = _curve_kwargs(self.hass, self._instance)
        now_ts = time.time()
        computed_phase = phase_at(now_ts, boundaries["morning_ts"], boundaries["day_ts"], boundaries["evening_ts"], boundaries["night_ts"])
        phase = _phase_override(self.hass, self._instance.override_entity_id) or computed_phase
        targets = targets_for_phase(
            phase,
            now_ts,
            boundaries["evening_ts"],
            boundaries["day_ts"],
            boundaries["night_ts"],
            boundaries["morning_ts"],
            **curve_kwargs,
        )
        return {
            **boundaries,
            "phase": phase,
            "computed_phase": computed_phase,
            "brightness": targets["brightness"],
            "kelvin": targets["kelvin"],
            "rgb_color": targets["rgb_color"],
            "points": _compute_curve_points(boundaries, curve_kwargs),
        }
