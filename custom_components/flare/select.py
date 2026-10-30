"""Phase override select, one per schedule. Self-clearing: an override
holds until the computed phase next changes, then returns to Auto -
unless switch.<prefix>sticky_phase_override is on."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.select import SelectEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import PHASE_AUTO, PHASE_OPTIONS
from .schedule.coordinator import PHASE_OVERRIDE_ROLE, ScheduleCoordinator, ScheduleInstance, schedule_instances


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    for instance in schedule_instances(entry):
        coordinator: ScheduleCoordinator = entry.runtime_data[instance.subentry_id]
        async_add_entities([_PhaseOverrideSelect(coordinator, instance)], config_subentry_id=instance.subentry_id)


class _PhaseOverrideSelect(CoordinatorEntity[ScheduleCoordinator], SelectEntity, RestoreEntity):
    _attr_icon = "mdi:sun-clock"
    _attr_options = PHASE_OPTIONS
    _attr_has_entity_name = True

    def __init__(self, coordinator: ScheduleCoordinator, instance: ScheduleInstance) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = instance.unique_id(PHASE_OVERRIDE_ROLE)
        self._attr_translation_key = PHASE_OVERRIDE_ROLE
        self.entity_id = instance.override_entity_id
        self._attr_device_info = instance.device_info
        self._attr_current_option = PHASE_AUTO
        self._instance = instance
        # computed_phase when the override was set; once it moves on, the
        # override clears. None while Auto.
        self._baseline_phase: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in PHASE_OPTIONS:
            self._attr_current_option = last_state.state
        if self._attr_current_option != PHASE_AUTO:
            # The original baseline isn't persisted, so use now.
            self._baseline_phase = self.coordinator.data.computed_phase
            # The first refresh predates this entity, so it missed the
            # restored override.
            await self.coordinator.async_request_refresh()

    @property
    def _sticky(self) -> bool:
        state = self.hass.states.get(self._instance.sticky_entity(self.hass))
        return state is not None and state.state == STATE_ON

    def _handle_coordinator_update(self) -> None:
        if (
            not self._sticky
            and self._attr_current_option != PHASE_AUTO
            and self._baseline_phase is not None
            and self.coordinator.data.computed_phase != self._baseline_phase
        ):
            self._attr_current_option = PHASE_AUTO
            self._baseline_phase = None
            # This update's data still reflects the override. The refresh is
            # debounced, so the sensor catches up within 10s.
            self.hass.async_create_task(self.coordinator.async_request_refresh())
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._baseline_phase = self.coordinator.data.computed_phase if option != PHASE_AUTO else None
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
