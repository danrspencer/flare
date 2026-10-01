"""Sensor platform for both entries.

Schedules: sensor.<name>_flare per schedule. State is the phase; the
attributes carry the current brightness/color_temp/rgb_color, today's
boundaries, and the full-day `points` curve.

Tracking: per scope, the sensor holding its claims, plus
`controlled`/`overridden` counts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_TRACKING, EVENT_LIGHT_OVERRIDDEN
from .schedule.coordinator import ScheduleCoordinator, ScheduleInstance, schedule_instances
from .tracking.override_protection import classify
from .tracking.scope import StateInstance, state_instances
from .tracking.write_tracking import SIGNAL_WRITE_TRACKING_UPDATED, ClaimRegistry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_TRACKING:
        for instance in schedule_instances(entry):
            coordinator: ScheduleCoordinator = hass.data[DOMAIN][instance.subentry_id]
            async_add_entities([_ScheduleSensor(coordinator, instance)], config_subentry_id=instance.subentry_id)
        return

    registry: ClaimRegistry = hass.data[DOMAIN][entry.entry_id]
    for instance in state_instances(entry):
        async_add_entities(
            [
                _StateTrackingSensor(hass, registry, instance),
                _ScopeCountSensor(hass, registry, instance, "controlled"),
                _ScopeCountSensor(hass, registry, instance, "overridden"),
            ],
            config_subentry_id=instance.subentry_id,
        )


def _classify_tracked(hass: HomeAssistant, entity_id: str, record: dict) -> tuple[str, Any, Any]:
    """One light's status, shared by every sensor here so they agree.
    Returns (status, matched_via, live_context_id)."""
    state = hass.states.get(entity_id)
    live_context_id = state.context.id if state is not None else None
    if state is None or state.state in ("unavailable", "unknown"):
        return "unavailable", None, live_context_id
    raw_status, matched_via = classify(
        state.state == "on",
        record.get("observed"),
        record.get("latest"),
        live_context_id,
        state.attributes.get("brightness"),
        state.attributes.get("color_temp_kelvin"),
        state.attributes.get("rgb_color"),
        min_color_temp_kelvin=state.attributes.get("min_color_temp_kelvin"),
        max_color_temp_kelvin=state.attributes.get("max_color_temp_kelvin"),
    )
    # "untracked" shows as "controlled": either way, not excluded.
    return ("controlled" if raw_status == "untracked" else raw_status), matched_via, live_context_id



class _StateTrackingSensor(SensorEntity, RestoreEntity):
    """One scope's claims - the storage itself, published as an attribute.
    Kept out of the recorder but restored across a restart."""

    _attr_has_entity_name = True
    _attr_name = "Tracking"
    _attr_icon = "mdi:text-search"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "lights"
    # Polls too, since claims are judged against live state that changes
    # without any claim changing.
    _unrecorded_attributes = frozenset({"claims"})

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, instance: StateInstance) -> None:
        self.hass = hass
        self._registry = registry
        self._instance = instance
        self.claims: dict[str, dict] = {}
        self._last_statuses: dict[str, str] | None = None
        self._attr_unique_id = f"{instance.subentry_id}_tracking"
        self.entity_id = f"sensor.{instance.prefix}flare_tracking"
        self._attr_device_info = instance.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restored before registering, so no write lands in a dict about to be
        # replaced.
        last = await self.async_get_last_extra_data()
        if last is not None:
            self.claims = dict(last.as_dict().get("claims") or {})
        self._registry.register(self._instance.subentry_id, self)
        # The setup-time prune ran before this entity existed.
        await self._registry.async_prune_stale()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return RestoredExtraData({"claims": self.claims})

    async def async_will_remove_from_hass(self) -> None:
        self._registry.unregister(self._instance.subentry_id)

    @callback
    def async_claims_changed(self) -> None:
        self._refresh_statuses()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        self._refresh_statuses()
        # Counts depend on live state, not just claims.
        async_dispatcher_send(self.hass, SIGNAL_WRITE_TRACKING_UPDATED)

    @callback
    def _refresh_statuses(self) -> None:
        """Fires EVENT_LIGHT_OVERRIDDEN when a light becomes overridden, with the
        claims and live values at that moment. Not in extra_state_attributes,
        which HA reads on every state write."""
        statuses = {}
        for entity_id, record in self.claims.items():
            status, _via, live_context_id = _classify_tracked(self.hass, entity_id, record)
            statuses[entity_id] = status
            if self._last_statuses is None:
                continue
            if status == "overridden" and self._last_statuses.get(entity_id) != "overridden":
                self._fire_overridden(entity_id, record, self._last_statuses.get(entity_id), live_context_id)
        # The first pass seeds without firing, so a restart doesn't re-announce.
        self._last_statuses = statuses

    @callback
    def _fire_overridden(
        self, entity_id: str, record: dict, previous: str | None, live_context_id: str | None
    ) -> None:
        state = self.hass.states.get(entity_id)
        # Identifiers are only unique per config entry.
        device = None
        if self.registry_entry is not None and self.registry_entry.config_entry_id is not None:
            identifier = next(iter(self._instance.device_info["identifiers"]))
            device = dr.async_get(self.hass).async_get_device_by_identifier(
                identifier, self.registry_entry.config_entry_id
            )
        self.hass.bus.async_fire(
            EVENT_LIGHT_OVERRIDDEN,
            {
                "entity_id": entity_id,
                # device_id puts the event in the device's Activity; omitted, not None,
                # if the device isn't registered.
                "scope": self._instance.title,
                **({"device_id": device.id} if device else {}),
                "previous_status": previous,
                "live_context_id": live_context_id,
                "live": {
                    "state": state.state if state else None,
                    "brightness": state.attributes.get("brightness") if state else None,
                    "color_temp_kelvin": state.attributes.get("color_temp_kelvin") if state else None,
                    "rgb_color": state.attributes.get("rgb_color") if state else None,
                },
                "observed": record.get("observed"),
                "latest": record.get("latest"),
            },
        )

    @property
    def native_value(self) -> int:
        return len(self.claims)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"claims": self.claims}


class _ScopeCountSensor(SensorEntity):
    """How many of a scope's lights are in one status. They needn't sum to
    the total: an unavailable light is in neither."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "lights"
    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, registry: ClaimRegistry, instance: StateInstance, status: str
    ) -> None:
        self.hass = hass
        self._registry = registry
        self._instance = instance
        self._status = status
        self._attr_icon = "mdi:lightbulb-group" if status == "controlled" else "mdi:lightbulb-alert-outline"
        self._attr_unique_id = f"{instance.subentry_id}_{status}"
        self.entity_id = f"sensor.{instance.prefix}flare_{status}"
        self._attr_name = status.title()
        self._attr_device_info = instance.device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_WRITE_TRACKING_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _matching_lights(self) -> tuple[list[str], int]:
        lights: list[str] = []
        records = self._registry.records_for_scope(self._instance.subentry_id)
        for entity_id, record in records.items():
            status, _via, _ctx = _classify_tracked(self.hass, entity_id, record)
            if status == self._status:
                lights.append(entity_id)
        return sorted(lights), len(records)

    @property
    def native_value(self) -> int:
        return len(self._matching_lights()[0])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        lights, total = self._matching_lights()
        return {"lights": lights, "total_tracked": total}


class _ScheduleSensor(CoordinatorEntity[ScheduleCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:home-lightbulb"
    _attr_name = None  # the entity that represents the device - displays as just the device's own name
    # Over the recorder's attribute size limit, and only read live.
    _unrecorded_attributes = frozenset({"points"})

    def __init__(self, coordinator: ScheduleCoordinator, instance: ScheduleInstance) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{instance.subentry_id}_flare"
        self.entity_id = f"sensor.{instance.prefix}flare"
        self._attr_device_info = instance.device_info

    @property
    def native_value(self):
        return self.coordinator.data.get("phase")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        rgb_color = data.get("rgb_color")
        return {
            "phase": data.get("phase"),
            "brightness": data.get("brightness"),
            "color_temp": data.get("kelvin"),
            # A list, as the rgb_color service fields expect.
            "rgb_color": list(rgb_color) if rgb_color is not None else None,
            "morning_start": data.get("morning_ts"),
            "day_start": data.get("day_ts"),
            "evening_start": data.get("evening_ts"),
            "night_start": data.get("night_ts"),
            "evening_earliest": data.get("evening_earliest_ts"),
            "evening_latest": data.get("evening_latest_ts"),
            "points": data.get("points"),
        }

