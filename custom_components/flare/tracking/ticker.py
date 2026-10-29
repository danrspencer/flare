"""Each area's tick: when the automations for that area re-check their
lights. One scheduler spaces the areas across the interval, so their
writes don't reach the radio all at once. Area k fires k gaps after each
interval boundary; the gap shrinks when the areas wouldn't otherwise fit."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util


def slot_offsets(count: int, interval_minutes: int, gap_seconds: float) -> list[timedelta]:
    """How far past each boundary the `count` areas fire, in order."""
    if not count:
        return []
    step = min(timedelta(seconds=gap_seconds), timedelta(minutes=interval_minutes) / count)
    return [step * k for k in range(count)]


def next_tick(now: datetime, interval_minutes: int, offset: timedelta) -> datetime:
    """The first moment after `now` that is `offset` past a boundary.
    Boundaries are every `interval_minutes` from the Unix epoch, so on the
    clock's minutes."""
    period = interval_minutes * 60
    shift = offset.total_seconds()
    previous = math.floor((now.timestamp() - shift) / period) * period + shift
    return datetime.fromtimestamp(previous + period, tz=UTC)


class TickScheduler:
    """Fires each registered area once per interval, in title order."""

    def __init__(self, hass: HomeAssistant, interval_minutes: int, gap_seconds: float) -> None:
        self._hass = hass
        self._interval = interval_minutes
        self._gap = gap_seconds
        self._areas: dict[str, tuple[str, Callable[[], None]]] = {}
        self._timers: dict[str, CALLBACK_TYPE] = {}

    @callback
    def set_areas(self, areas: dict[str, tuple[str, Callable[[], None]]]) -> None:
        """Ticks exactly these areas (key -> (title, fire)), respaced."""
        self._areas = dict(areas)
        self._reschedule()

    @callback
    def stop(self) -> None:
        self._areas.clear()
        self._cancel_timers()

    @callback
    def _cancel_timers(self) -> None:
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    @callback
    def _reschedule(self) -> None:
        self._cancel_timers()
        ordered = sorted(self._areas, key=lambda key: (self._areas[key][0], key))
        now = dt_util.utcnow()
        for key, offset in zip(ordered, slot_offsets(len(ordered), self._interval, self._gap)):
            self._arm(key, offset, now)

    @callback
    def _arm(self, key: str, offset: timedelta, after: datetime) -> None:
        @callback
        def _fire(when: datetime) -> None:
            self._arm(key, offset, max(when, dt_util.utcnow()))
            self._areas[key][1]()

        self._timers[key] = async_track_point_in_utc_time(
            self._hass, _fire, next_tick(after, self._interval, offset)
        )
