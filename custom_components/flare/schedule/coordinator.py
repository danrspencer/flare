"""Schedule coordinator, one per schedule sensor, shared by that schedule's
entities. Reads the schedule's time/number entities live on every update.

Evening starts at sunset, clamped between the earliest/latest bounds.
A phase override changes the "right now" values but not the full-day
curve (`points`)."""

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

# Also each time entity's entity_id suffix.
TIME_KEYS = (
    "morning_time",
    "day_time",
    "evening_earliest_time",
    "evening_latest_time",
    "night_time",
)

# Also each number entity's entity_id suffix, and the compute_curve
# schema's field order.
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
    """One schedule sensor, from a "sensor" subentry."""

    subentry_id: str  # hass.data storage key; also passed to async_add_entities(config_subentry_id=...)
    # "<slug>_", or empty if the name slugifies to nothing.
    prefix: str
    override_entity_id: str  # select.<prefix>flare_phase
    sticky_entity_id: str  # switch.<prefix>sticky_phase_override
    title: str  # the subentry's name (required - see SensorSubentryFlow)

    @property
    def device_info(self) -> DeviceInfo:
        """With has_entity_name, renaming the device renames every entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.subentry_id)},
            name=self.title or "Adaptive Lighting",
            entry_type=DeviceEntryType.SERVICE,
            # Lets the blueprint's device selector offer only schedules.
            model="Schedule",
        )

    def time_entity_id(self, key: str) -> str:
        return f"time.{self.prefix}{key}"

    def number_entity_id(self, key: str) -> str:
        return f"number.{self.prefix}{key}"


def schedule_instances(entry: ConfigEntry) -> list[ScheduleInstance]:
    """One per "sensor" subentry."""
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
    """A time entity's "HH:MM:SS" as today's local timestamp."""
    if not time_str:
        return None
    t = dt_util.parse_time(time_str)
    if t is None:
        return None
    now_local = dt_util.now()
    return now_local.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0).timestamp()


def _time_ts(hass: HomeAssistant, instance: ScheduleInstance, key: str) -> float:
    """Today's timestamp for one boundary, never None: falls back to the
    default when the entity doesn't exist yet or is unavailable, as it is
    during a reload. None would crash phase_at() and wedge setup."""
    state = hass.states.get(instance.time_entity_id(key))
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
        # next_setting is tomorrow's once today's sunset has passed, so use its
        # time of day, projected onto today.
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
