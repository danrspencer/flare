"""Curve values and transition lengths as number entities, one per
CURVE_KEYS per schedule. A transition belongs to the phase it runs in:
"Day Colour Transition" is how long before Day ends to start easing to
Evening's colour."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .schedule.coordinator import CURVE_KEYS, ScheduleCoordinator, ScheduleInstance, schedule_instances
from .schedule.curve import DEFAULT_CURVE_VALUES, value_range


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    for instance in schedule_instances(entry):
        coordinator: ScheduleCoordinator = entry.runtime_data[instance.subentry_id]
        entities = [_CurveNumber(coordinator, instance, key) for key in CURVE_KEYS]
        async_add_entities(entities, config_subentry_id=instance.subentry_id)


class _CurveNumber(RestoreNumber, NumberEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = "box"

    def __init__(self, coordinator: ScheduleCoordinator, instance: ScheduleInstance, key: str) -> None:
        self._coordinator = coordinator
        self._key = key
        self._attr_unique_id = instance.unique_id(key)
        self._attr_translation_key = key
        self.entity_id = instance.number_entity_id(key)
        self._attr_device_info = instance.device_info
        self._attr_native_min_value, self._attr_native_max_value = value_range(key)
        self._attr_native_step = 1
        if key.endswith("_transition"):
            self._attr_native_unit_of_measurement = "min"
        elif key.endswith("_kelvin"):
            self._attr_native_unit_of_measurement = "K"
        self._attr_native_value = DEFAULT_CURVE_VALUES[key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None and last_data.native_value is not None:
            self._attr_native_value = last_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        # Refresh rather than wait for the next poll (debounced: at most 10s).
        await self._coordinator.async_request_refresh()
