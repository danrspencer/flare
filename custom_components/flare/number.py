"""Curve values and transition lengths as number entities, one per
CURVE_KEYS per schedule."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .schedule.coordinator import CURVE_KEYS, ScheduleCoordinator, ScheduleInstance, schedule_instances
from .schedule.curve import DEFAULT_CURVE_VALUES, value_range

_LABELS = {
    "morning_brightness": "Morning Brightness",
    "morning_kelvin": "Morning Colour Temperature",
    "day_brightness": "Day Brightness",
    "day_kelvin": "Day Colour Temperature",
    "evening_brightness": "Evening Brightness",
    "evening_kelvin": "Evening Colour Temperature",
    "night_brightness": "Night Brightness",
    "night_kelvin": "Night Colour Temperature",
    # A transition belongs to the phase it runs in: "Day Colour Transition"
    # is how long before Day ends to start easing to Evening's colour.
    "morning_brightness_transition": "Morning Brightness Transition",
    "morning_kelvin_transition": "Morning Colour Transition",
    "day_brightness_transition": "Day Brightness Transition",
    "day_kelvin_transition": "Day Colour Transition",
    "evening_brightness_transition": "Evening Brightness Transition",
    "evening_kelvin_transition": "Evening Colour Transition",
    "night_brightness_transition": "Night Brightness Transition",
    "night_kelvin_transition": "Night Colour Transition",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    for instance in schedule_instances(entry):
        coordinator: ScheduleCoordinator = hass.data[DOMAIN][instance.subentry_id]
        entities = [_CurveNumber(coordinator, instance, key) for key in CURVE_KEYS]
        async_add_entities(entities, config_subentry_id=instance.subentry_id)


class _CurveNumber(RestoreNumber, NumberEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = "box"

    def __init__(self, coordinator: ScheduleCoordinator, instance: ScheduleInstance, key: str) -> None:
        self._coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{instance.subentry_id}_{key}"
        self.entity_id = instance.number_entity_id(key)
        self._attr_device_info = instance.device_info
        self._attr_name = _LABELS[key]
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
