"""Each zone's tick: when its automation re-checks its lights. One
scheduler spaces the zones across the interval, so their writes don't
reach the radio all at once. Zone k fires k gaps after each interval
boundary; the gap shrinks when the zones wouldn't otherwise fit."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util


def slot_offsets(count: int, interval_minutes: int, gap_seconds: float) -> list[timedelta]:
    """How far past each boundary the `count` zones fire, in order."""
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
    """Fires each registered zone once per interval, in title order."""

    def __init__(self, hass: HomeAssistant, interval_minutes: int, gap_seconds: float) -> None:
        self._hass = hass
        self._interval = interval_minutes
        self._gap = gap_seconds
        self._zones: dict[str, tuple[str, Callable[[], None]]] = {}
        self._timers: dict[str, CALLBACK_TYPE] = {}

    @callback
    def register(self, key: str, title: str, fire: Callable[[], None]) -> CALLBACK_TYPE:
        """Adds a zone, respacing every zone. Returns its unregister."""
        self._zones[key] = (title, fire)
        self._reschedule()

        @callback
        def _unregister() -> None:
            self._zones.pop(key, None)
            self._reschedule()

        return _unregister

    @callback
    def stop(self) -> None:
        self._zones.clear()
        self._cancel_timers()

    @callback
    def _cancel_timers(self) -> None:
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    @callback
    def _reschedule(self) -> None:
        self._cancel_timers()
        ordered = sorted(self._zones, key=lambda key: (self._zones[key][0], key))
        now = dt_util.utcnow()
        for key, offset in zip(ordered, slot_offsets(len(ordered), self._interval, self._gap)):
            self._arm(key, offset, now)

    @callback
    def _arm(self, key: str, offset: timedelta, after: datetime) -> None:
        @callback
        def _fire(when: datetime) -> None:
            self._arm(key, offset, max(when, dt_util.utcnow()))
            self._zones[key][1]()

        self._timers[key] = async_track_point_in_utc_time(
            self._hass, _fire, next_tick(after, self._interval, offset)
        )
