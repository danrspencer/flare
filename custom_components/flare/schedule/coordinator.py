"""Schedule coordinator, one per schedule sensor, shared by that schedule's
entities. Reads the schedule's time/number entities live on every update.

Evening starts at sunset, clamped between the earliest/latest bounds.
A phase override changes the "right now" values but not the full-day
curve (`points`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time as time_of_day
from datetime import timedelta

from homeassistant.components.number import ENTITY_ID_FORMAT as NUMBER_ENTITY_ID
from homeassistant.components.select import ENTITY_ID_FORMAT as SELECT_ENTITY_ID
from homeassistant.components.switch import ENTITY_ID_FORMAT as SWITCH_ENTITY_ID
from homeassistant.components.time import ENTITY_ID_FORMAT as TIME_ENTITY_ID
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify
import homeassistant.util.dt as dt_util

from ..const import DOMAIN, PHASE_AUTO, SUBENTRY_TYPE_SENSOR, Phase, is_reachable
from .curve import DEFAULT_CURVE_VALUES, DEFAULT_SCHEDULE_HOURS, phase_at, targets_for_phase

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=60)

# Roles: each entity's unique ID suffix and translation key, which the
# dashboard finds it by.
PHASE_OVERRIDE_ROLE = "phase_override"
STICKY_PHASE_OVERRIDE_ROLE = "sticky_phase_override"
PHASE_EVENT_ROLE = "phase_event"
# The object ID the phase override select and the Phase event share.
PHASE_OBJECT_ID = "flare_phase"

# Each time entity's role, and its entity_id suffix.
MORNING_TIME = "morning_time"
DAY_TIME = "day_time"
EVENING_EARLIEST_TIME = "evening_earliest_time"
EVENING_LATEST_TIME = "evening_latest_time"
NIGHT_TIME = "night_time"
TIME_KEYS = (MORNING_TIME, DAY_TIME, EVENING_EARLIEST_TIME, EVENING_LATEST_TIME, NIGHT_TIME)

# Also each number entity's entity_id suffix, and the compute_curve
# schema's field order.
CURVE_KEYS = tuple(DEFAULT_CURVE_VALUES)


@dataclass
class ScheduleInstance:
    """One schedule sensor, from a "sensor" subentry."""

    subentry_id: str  # its coordinator's key in entry.runtime_data; also passed to async_add_entities(config_subentry_id=...)
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
            name=self.title,
            entry_type=DeviceEntryType.SERVICE,
            # Lets the blueprint's device selector offer only schedules.
            model="Schedule",
        )

    def time_entity_id(self, key: str) -> str:
        """The ID it's created with; read it through time_entity()."""
        return TIME_ENTITY_ID.format(f"{self.prefix}{key}")

    def number_entity_id(self, key: str) -> str:
        """The ID it's created with; read it through number_entity()."""
        return NUMBER_ENTITY_ID.format(f"{self.prefix}{key}")

    def unique_id(self, role: str) -> str:
        return f"{self.subentry_id}_{role}"

    def current_id(self, hass: HomeAssistant, entity_id: str, role: str) -> str:
        """The entity's ID now, found by its unique ID so one the user renamed
        is still read. `entity_id` until it's registered."""
        domain = split_entity_id(entity_id)[0]
        return er.async_get(hass).async_get_entity_id(domain, DOMAIN, self.unique_id(role)) or entity_id

    def time_entity(self, hass: HomeAssistant, key: str) -> str:
        return self.current_id(hass, self.time_entity_id(key), key)

    def number_entity(self, hass: HomeAssistant, key: str) -> str:
        return self.current_id(hass, self.number_entity_id(key), key)

    def override_entity(self, hass: HomeAssistant) -> str:
        return self.current_id(hass, self.override_entity_id, PHASE_OVERRIDE_ROLE)

    def sticky_entity(self, hass: HomeAssistant) -> str:
        return self.current_id(hass, self.sticky_entity_id, STICKY_PHASE_OVERRIDE_ROLE)


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
                override_entity_id=SELECT_ENTITY_ID.format(f"{prefix}{PHASE_OBJECT_ID}"),
                sticky_entity_id=SWITCH_ENTITY_ID.format(f"{prefix}{STICKY_PHASE_OVERRIDE_ROLE}"),
                title=subentry.title,
            )
        )
    return instances


def default_time(key: str) -> time_of_day:
    """A boundary's default: "morning_time" -> DEFAULT_SCHEDULE_HOURS["morning"]."""
    return time_of_day(hour=DEFAULT_SCHEDULE_HOURS[key[: -len("_time")]])


def read_schedule(hass: HomeAssistant, instance: ScheduleInstance) -> dict[str, str | int]:
    """The schedule's values as its entities hold them now: times as
    "HH:MM:SS", curve values as ints. Anything unreachable or unreadable is
    left out, for the caller to default (the curve) or omit (an export)."""
    values: dict[str, str | int] = {}
    for key in TIME_KEYS:
        state = hass.states.get(instance.time_entity(hass, key))
        if is_reachable(state) and dt_util.parse_time(state.state) is not None:
            values[key] = state.state
    for key in CURVE_KEYS:
        state = hass.states.get(instance.number_entity(hass, key))
        if not is_reachable(state):
            continue
        try:
            values[key] = round(float(state.state))
        except (TypeError, ValueError):
            continue
    return values


def _time_str_to_today_timestamp(time_str: str | None) -> float | None:
    """A time entity's "HH:MM:SS" as today's local timestamp."""
    if not time_str:
        return None
    t = dt_util.parse_time(time_str)
    if t is None:
        return None
    now_local = dt_util.now()
    return now_local.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0).timestamp()


@dataclass(frozen=True)
class Boundaries:
    """Today's boundary timestamps, Evening's two limits included."""

    morning: float
    day: float
    evening: float
    night: float
    evening_earliest: float
    evening_latest: float


@dataclass(frozen=True)
class ScheduleData:
    """What a schedule's coordinator works out on each update."""

    boundaries: Boundaries
    # The override's phase while one is set, else computed_phase.
    phase: str
    computed_phase: Phase
    brightness: int
    kelvin: int
    rgb_color: tuple[int, int, int]
    points: list[dict[str, int]]


def _compute_boundaries(hass: HomeAssistant, instance: ScheduleInstance) -> Boundaries:
    """Today's boundary timestamps. A boundary not read falls back to its
    default, as during a reload: a gap would crash phase_at() and wedge setup."""
    values = read_schedule(hass, instance)

    def time_ts(key: str) -> float:
        return _time_str_to_today_timestamp(values.get(key) or default_time(key).isoformat())

    morning_ts = time_ts(MORNING_TIME)
    day_ts = time_ts(DAY_TIME)
    night_ts = time_ts(NIGHT_TIME)
    earliest_ts = time_ts(EVENING_EARLIEST_TIME)
    latest_ts = time_ts(EVENING_LATEST_TIME)

    # Today's sunset where the home is; none on a day the sun doesn't set.
    sunset = get_astral_event_date(hass, "sunset", dt_util.now().date())
    sunset_ts = sunset.timestamp() if sunset is not None else latest_ts

    evening_ts = max(earliest_ts, min(sunset_ts, latest_ts))

    return Boundaries(
        morning=morning_ts,
        day=day_ts,
        evening=evening_ts,
        night=night_ts,
        evening_earliest=earliest_ts,
        evening_latest=latest_ts,
    )


def _compute_curve_points(boundaries: Boundaries, curve_kwargs: dict[str, int]) -> list[dict[str, int]]:
    morning_ts, day_ts, evening_ts, night_ts = boundaries.morning, boundaries.day, boundaries.evening, boundaries.night
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


def _phase_override(hass: HomeAssistant, instance: ScheduleInstance) -> str | None:
    state = hass.states.get(instance.override_entity(hass))
    if not is_reachable(state) or state.state == PHASE_AUTO:
        return None
    return state.state


class ScheduleCoordinator(DataUpdateCoordinator[ScheduleData]):
    def __init__(self, hass: HomeAssistant, instance: ScheduleInstance) -> None:
        super().__init__(hass, _LOGGER, name=f"FLARE schedule ({instance.title})", update_interval=UPDATE_INTERVAL)
        self._instance = instance

    async def _async_update_data(self) -> ScheduleData:
        boundaries = _compute_boundaries(self.hass, self._instance)
        values = read_schedule(self.hass, self._instance)
        curve_kwargs = {key: values[key] for key in CURVE_KEYS if key in values}
        now_ts = dt_util.utcnow().timestamp()
        computed_phase = phase_at(now_ts, boundaries.morning, boundaries.day, boundaries.evening, boundaries.night)
        phase = _phase_override(self.hass, self._instance) or computed_phase
        targets = targets_for_phase(
            phase,
            now_ts,
            boundaries.evening,
            boundaries.day,
            boundaries.night,
            boundaries.morning,
            **curve_kwargs,
        )
        return ScheduleData(
            boundaries=boundaries,
            phase=phase,
            computed_phase=computed_phase,
            brightness=targets["brightness"],
            kelvin=targets["kelvin"],
            rgb_color=targets["rgb_color"],
            points=_compute_curve_points(boundaries, curve_kwargs),
        )
