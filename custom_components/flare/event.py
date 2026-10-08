"""Each schedule's "Phase" event entity, fired with the phase's name
whenever it changes.

The blueprint triggers on it through the schedule's device, so it has no
entity_category: target expansion through a device skips categorised
entities."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_ZONES, PHASES
from .schedule.coordinator import ScheduleCoordinator, ScheduleInstance, schedule_instances


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ZONES:
        return
    for instance in schedule_instances(entry):
        coordinator: ScheduleCoordinator = hass.data[DOMAIN][instance.subentry_id]
        async_add_entities([_SchedulePhase(coordinator, instance)], config_subentry_id=instance.subentry_id)


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
        self._attr_translation_key = "phase_event"
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
