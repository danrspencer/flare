"""A real Schedules entry: its entities, the values its sensor publishes,
config changes taking effect at once, and the phase override."""

from datetime import datetime, time, timedelta

import pytest
from freezegun import freeze_time
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SCHEDULES, SUBENTRY_TYPE_SENSOR
from custom_components.flare.schedule.coordinator import CURVE_KEYS, TIME_KEYS, ScheduleCoordinator

SENSOR = "sensor.ground_floor_flare"
SELECT = "select.ground_floor_flare_phase"
STICKY = "switch.ground_floor_sticky_phase_override"
PHASE = "event.ground_floor_flare_phase"


def _today_at(hour: int, minute: int = 0) -> datetime:
    return dt_util.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


@pytest.fixture
def frozen(hass: HomeAssistant):
    """Noon today (local), with the event loop left on the real clock."""
    noon = dt_util.now().replace(hour=12, minute=0, second=0, microsecond=0)
    with freeze_time(noon, real_asyncio=True) as frozen:
        yield frozen


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}",
        version=3,
        subentries_data=[ConfigSubentryData(subentry_type=SUBENTRY_TYPE_SENSOR, title="Ground Floor", unique_id="ground_floor", data={})],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _move_to(hass: HomeAssistant, frozen, when: datetime) -> None:
    """Move the clock and let the 60s poll run."""
    frozen.move_to(when)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()


def _attr(hass: HomeAssistant, name: str):
    return hass.states.get(SENSOR).attributes[name]


@pytest.fixture
async def schedule(stub_entry_setup, frozen, hass: HomeAssistant):
    return await _setup(hass)


async def test_every_entity_is_created(schedule, hass: HomeAssistant):
    expected = [SENSOR, SELECT, STICKY, PHASE]
    expected += [f"time.ground_floor_{key}" for key in TIME_KEYS]
    expected += [f"number.ground_floor_{key}" for key in CURVE_KEYS]
    assert [e for e in expected if hass.states.get(e) is None] == []


async def test_the_sensor_publishes_the_current_values_and_the_day(schedule, hass: HomeAssistant):
    state = hass.states.get(SENSOR)
    assert state.state == "Day"
    assert state.attributes["phase"] == "Day"
    assert state.attributes["brightness"] == 255
    assert isinstance(state.attributes["rgb_color"], list)
    assert len(state.attributes["points"]) == 289
    assert dt_util.utc_from_timestamp(state.attributes["night_start"]) == _today_at(22)


async def test_a_curve_value_change_applies_at_once(schedule, hass: HomeAssistant):
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.ground_floor_day_brightness", "value": 100}, blocking=True
    )
    await hass.async_block_till_done()

    assert _attr(hass, "brightness") == 100


async def test_a_boundary_change_applies_at_once(schedule, hass: HomeAssistant):
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.ground_floor_day_time", "time": time(13, 0)}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(SENSOR).state == "Morning"


class TestPhaseEvent:
    """What the blueprint triggers on: one event per real phase change."""

    async def test_it_fires_the_current_phase_once_set_up(self, schedule, hass: HomeAssistant):
        assert hass.states.get(PHASE).attributes["event_type"] == "Day"

    async def test_a_value_change_within_the_phase_does_not_fire_it(self, schedule, hass: HomeAssistant):
        fired_at = hass.states.get(PHASE).state

        await hass.services.async_call(
            "number", "set_value", {"entity_id": "number.ground_floor_day_brightness", "value": 100}, blocking=True
        )
        await hass.async_block_till_done()

        assert _attr(hass, "brightness") == 100, "precondition: the sensor did update"
        assert hass.states.get(PHASE).state == fired_at

    async def test_a_phase_change_fires_it(self, schedule, hass: HomeAssistant):
        await hass.services.async_call(
            "time", "set_value", {"entity_id": "time.ground_floor_day_time", "time": time(13, 0)}, blocking=True
        )
        await hass.async_block_till_done()

        assert hass.states.get(PHASE).attributes["event_type"] == "Morning"

    async def test_the_sensor_already_shows_the_phase_when_it_fires(self, schedule, hass: HomeAssistant):
        """An automation it triggers reads the sensor straight away."""
        seen: list[tuple[str, str]] = []

        @callback
        def _fired(event) -> None:
            seen.append((event.data["new_state"].attributes["event_type"], hass.states.get(SENSOR).state))

        async_track_state_change_event(hass, [PHASE], _fired)
        # The order that loses: the Phase entity hears the refresh before
        # the sensor does. Which comes first otherwise depends on setup order.
        coordinator = next(v for v in hass.data[DOMAIN].values() if isinstance(v, ScheduleCoordinator))
        coordinator._listeners = dict(
            sorted(coordinator._listeners.items(), key=lambda item: getattr(item[1][0], "__self__", None) is None
                   or item[1][0].__self__.entity_id != PHASE)
        )
        await hass.services.async_call("select", "select_option", {"entity_id": SELECT, "option": "Night"}, blocking=True)
        await hass.async_block_till_done()

        assert seen == [("Night", "Night")]

    async def test_an_override_fires_it(self, schedule, hass: HomeAssistant):
        await hass.services.async_call("select", "select_option", {"entity_id": SELECT, "option": "Night"}, blocking=True)
        await hass.async_block_till_done()

        assert hass.states.get(PHASE).attributes["event_type"] == "Night"


class TestPhaseOverride:
    async def test_selecting_a_phase_applies_it(self, schedule, hass: HomeAssistant):
        await hass.services.async_call("select", "select_option", {"entity_id": SELECT, "option": "Night"}, blocking=True)
        await hass.async_block_till_done()

        assert hass.states.get(SENSOR).state == "Night"
        assert _attr(hass, "brightness") == 80

    async def test_it_clears_itself_when_the_schedule_moves_on(self, schedule, frozen, hass: HomeAssistant):
        await hass.services.async_call("select", "select_option", {"entity_id": SELECT, "option": "Night"}, blocking=True)
        await _move_to(hass, frozen, _today_at(21))  # Day -> Evening (no sun.sun: starts at 20:00)
        assert hass.states.get(SELECT).state == "Auto"

        # The follow-up refresh is debounced (10s cooldown after the poll).
        await _move_to(hass, frozen, _today_at(21) + timedelta(seconds=11))
        assert hass.states.get(SENSOR).state == "Evening"

    async def test_sticky_keeps_it_past_the_boundary(self, schedule, frozen, hass: HomeAssistant):
        await hass.services.async_call("switch", "turn_on", {"entity_id": STICKY}, blocking=True)
        await hass.services.async_call("select", "select_option", {"entity_id": SELECT, "option": "Night"}, blocking=True)
        await _move_to(hass, frozen, _today_at(21))

        assert hass.states.get(SELECT).state == "Night"
        assert hass.states.get(SENSOR).state == "Night"


class TestEveningFollowsSunset:
    """Clamped between Evening Earliest (17:00) and Evening Latest (20:00)."""

    async def _with_sunset(self, hass: HomeAssistant, next_setting: datetime):
        hass.states.async_set("sun.sun", "above_horizon", {"next_setting": next_setting.isoformat()})
        await hass.async_block_till_done()
        return dt_util.utc_from_timestamp(_attr(hass, "evening_start"))

    async def test_sunset_within_the_window(self, schedule, hass: HomeAssistant):
        assert await self._with_sunset(hass, _today_at(18, 30)) == _today_at(18, 30)

    @pytest.mark.parametrize(("sunset", "clamped"), [((16, 0), (17, 0)), ((21, 30), (20, 0))], ids=["early", "late"])
    async def test_sunset_outside_the_window_is_clamped(self, schedule, hass: HomeAssistant, sunset, clamped):
        assert await self._with_sunset(hass, _today_at(*sunset)) == _today_at(*clamped)

    async def test_once_sunset_has_passed_tomorrows_time_is_used_for_today(self, schedule, hass: HomeAssistant):
        """next_setting points at tomorrow after today's sunset; comparing
        it directly would clamp to the latest bound."""
        assert await self._with_sunset(hass, _today_at(18, 30) + timedelta(days=1)) == _today_at(18, 30)
