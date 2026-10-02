"""Event entities, one platform for both entries.

Zones: a "Tick", fired by the zone scheduler (see zone/ticker.py).
Schedules: a "Phase", fired with the phase's name whenever it changes.

The blueprint triggers on both through the device it was given, so they
have no entity_category: target expansion through a device skips
categorised entities."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_ZONES, EVENT_TYPE_TICK, PHASES
from .schedule.coordinator import ScheduleCoordinator, ScheduleInstance, schedule_instances
from .zone.instance import ZoneInstance, zone_instances
from .zone.ticker import TickScheduler


def ticks_key(entry: ConfigEntry) -> str:
    """The scheduler's key in hass.data[DOMAIN]."""
    return f"{entry.entry_id}_ticks"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_ZONES:
        for instance in schedule_instances(entry):
            coordinator: ScheduleCoordinator = hass.data[DOMAIN][instance.subentry_id]
            async_add_entities([_SchedulePhase(coordinator, instance)], config_subentry_id=instance.subentry_id)
        return

    scheduler: TickScheduler = hass.data[DOMAIN][ticks_key(entry)]
    for instance in zone_instances(entry):
        async_add_entities([_ZoneTick(scheduler, instance)], config_subentry_id=instance.subentry_id)


class _ZoneTick(EventEntity):
    _attr_has_entity_name = True
    _attr_name = "Tick"
    _attr_icon = "mdi:metronome"
    _attr_event_types = [EVENT_TYPE_TICK]
    _attr_should_poll = False

    def __init__(self, scheduler: TickScheduler, instance: ZoneInstance) -> None:
        self._scheduler = scheduler
        self._instance = instance
        self._attr_unique_id = f"{instance.subentry_id}_tick"
        self.entity_id = f"event.{instance.prefix}flare_tick"
        self._attr_device_info = instance.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._scheduler.register(self._instance.subentry_id, self._instance.title, self._tick)
        )

    @callback
    def _tick(self) -> None:
        self._trigger_event(EVENT_TYPE_TICK)
        self.async_write_ha_state()


class _SchedulePhase(CoordinatorEntity[ScheduleCoordinator], EventEntity):
    """Fires once per phase change, including a manual override, and once on
    the first refresh after setup."""

    _attr_has_entity_name = True
    _attr_name = "Phase"
    _attr_icon = "mdi:theme-light-dark"
    _attr_event_types = PHASES

    def __init__(self, coordinator: ScheduleCoordinator, instance: ScheduleInstance) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{instance.subentry_id}_phase_event"
        self.entity_id = f"event.{instance.prefix}flare_phase"
        self._attr_device_info = instance.device_info
        self._fired_phase: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        phase = (self.coordinator.data or {}).get("phase")
        if phase not in PHASES or phase == self._fired_phase:
            return
        self._fired_phase = phase
        # After the rest of this update's listeners, so the schedule sensor
        # already shows the new phase when a triggered automation reads it.
        self.hass.loop.call_soon(self._fire, phase)

    @callback
    def _fire(self, phase: str) -> None:
        if self.hass is None or self.platform is None:
            return
        self._trigger_event(phase)
        self.async_write_ha_state()
