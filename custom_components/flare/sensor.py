"""Sensor platform for both entries.

Schedules: sensor.<name>_flare per schedule. State is the phase; the
attributes carry the current brightness/color_temp/rgb_color, today's
boundaries, and the full-day `points` curve.

Zones: per zone, the sensor holding its claims, plus
`controlled`/`overridden` counts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_ZONES,
    EVENT_LIGHT_OVERRIDDEN,
    EVENT_LIGHTS_CONTROLLED,
    EVENT_LIGHTS_RELEASED,
)
from .schedule.coordinator import ScheduleCoordinator, ScheduleInstance, schedule_instances
from .zone.override_protection import RECONNECT_SETTLE, classify_state
from .zone.instance import ZoneInstance, zone_instances
from .zone.claims import SIGNAL_CLAIMS_UPDATED, ClaimRegistry, reconnected_at


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_ZONES:
        for instance in schedule_instances(entry):
            coordinator: ScheduleCoordinator = hass.data[DOMAIN][instance.subentry_id]
            async_add_entities([_ScheduleSensor(coordinator, instance)], config_subentry_id=instance.subentry_id)
        return

    registry: ClaimRegistry = hass.data[DOMAIN][entry.entry_id]
    for instance in zone_instances(entry):
        async_add_entities(
            [
                _ZoneClaimsSensor(hass, registry, instance),
                _ZoneCountSensor(hass, registry, instance, "controlled"),
                _ZoneCountSensor(hass, registry, instance, "overridden"),
            ],
            config_subentry_id=instance.subentry_id,
        )


def _classify_tracked(hass: HomeAssistant, entity_id: str, record: dict) -> tuple[str, Any, Any]:
    """One light's status, shared by every sensor here so they agree.
    Returns (status, matched_via, live_context_id)."""
    state = hass.states.get(entity_id)
    live_context_id = state.context.id if state is not None else None
    reconnected = reconnected_at(hass, entity_id)
    raw_status, matched_via = classify_state(state, record, reconnected_at=reconnected)
    # "untracked" shows as "controlled": either way, not excluded.
    status = "controlled" if raw_status == "untracked" else raw_status
    # A light just back online reports stale values before FLARE's resend
    # lands, so it isn't shown as overridden until it has settled.
    if status == "overridden" and reconnected is not None and dt_util.utcnow() < reconnected + RECONNECT_SETTLE:
        status = "settling"
    return status, matched_via, live_context_id



# How long a zone gathers lights it has taken before announcing them.
CONTROLLED_GATHER_SECONDS = 3


class _ZoneClaimsSensor(SensorEntity, RestoreEntity):
    """One zone's claims - the storage itself, published as an attribute.
    Kept out of the recorder but restored across a restart."""

    _attr_has_entity_name = True
    _attr_name = "Claims"
    _attr_icon = "mdi:text-search"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "lights"
    # Polls too, since claims are judged against live state that changes
    # without any claim changing.
    _unrecorded_attributes = frozenset({"claims"})

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, instance: ZoneInstance) -> None:
        self.hass = hass
        self._registry = registry
        self._instance = instance
        self.claims: dict[str, dict] = {}
        self._last_statuses: dict[str, str] | None = None
        self._newly_controlled: set[str] = set()
        self._announce_later = None
        self._recheck_later = None
        self._attr_unique_id = f"{instance.subentry_id}_claims"
        self.entity_id = f"sensor.{instance.prefix}flare_claims"
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
        for cancel in (self._announce_later, self._recheck_later):
            if cancel is not None:
                cancel()

    @callback
    def async_claims_changed(self) -> None:
        self._refresh_statuses()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        self._refresh_statuses()
        # Counts depend on live state, not just claims.
        async_dispatcher_send(self.hass, SIGNAL_CLAIMS_UPDATED)

    @callback
    def _refresh_statuses(self) -> None:
        """Fires EVENT_LIGHT_OVERRIDDEN when a light becomes overridden, with the
        claims and live values at that moment, and EVENT_LIGHTS_CONTROLLED
        when the zone takes lights it wasn't setting. A light becoming
        controlled again is churn, not news, so it's silent. Not in
        extra_state_attributes, which HA reads on every state write."""
        statuses = {}
        for entity_id, record in self.claims.items():
            status, _via, live_context_id = _classify_tracked(self.hass, entity_id, record)
            statuses[entity_id] = status
            if status == "settling":
                self._recheck_after_settling()
            if self._last_statuses is None:
                continue
            previous = self._last_statuses.get(entity_id)
            if status == "overridden" and previous != "overridden":
                self._fire_overridden(entity_id, record, previous, live_context_id)
            # Not back from overridden (churn), nor from unavailable or
            # settling (every light, after a restart), which were already
            # the zone's.
            elif status == "controlled" and previous not in ("controlled", "overridden", "unavailable", "settling"):
                self._controlled_soon(entity_id)
        # The first pass seeds without firing, so a restart doesn't re-announce.
        self._last_statuses = statuses

    @callback
    def _recheck_after_settling(self) -> None:
        if self._recheck_later is None:
            self._recheck_later = async_call_later(
                self.hass, RECONNECT_SETTLE.total_seconds() + 1, self._recheck
            )

    @callback
    def _recheck(self, _now) -> None:
        self._recheck_later = None
        self._refresh_statuses()
        # The counts settle too.
        async_dispatcher_send(self.hass, SIGNAL_CLAIMS_UPDATED)

    @callback
    def _fire_overridden(
        self, entity_id: str, record: dict, previous: str | None, live_context_id: str | None
    ) -> None:
        state = self.hass.states.get(entity_id)
        self.hass.bus.async_fire(
            EVENT_LIGHT_OVERRIDDEN,
            {
                "light": entity_id,
                **self._zone_data("overridden"),
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

    @callback
    def _controlled_soon(self, entity_id: str) -> None:
        """A room's lights report back one by one, so they're gathered for
        a moment and announced together."""
        self._newly_controlled.add(entity_id)
        if self._announce_later is None:
            self._announce_later = async_call_later(self.hass, CONTROLLED_GATHER_SECONDS, self._announce_controlled)

    @callback
    def _announce_controlled(self, _now) -> None:
        """Only lights that are on: a turn-off claims lights too, and taking a
        room's lights to switch them off isn't taking control of them."""
        self._announce_later = None
        gathered, self._newly_controlled = self._newly_controlled, set()
        statuses = self._last_statuses or {}
        lit = sorted(e for e, status in statuses.items() if status == "controlled" and self._is_on(e))
        lights = [e for e in lit if e in gathered]
        if not lights:
            return
        self.hass.bus.async_fire(
            EVENT_LIGHTS_CONTROLLED,
            {"lights": lights, "controlled": len(lit), **self._zone_data("controlled")},
        )

    @callback
    def async_announce_released(self, entity_ids: list[str]) -> None:
        """The zone let these go: dark, or Clear."""
        if not entity_ids:
            return
        self.hass.bus.async_fire(
            EVENT_LIGHTS_RELEASED, {"lights": entity_ids, **self._zone_data("controlled")}
        )

    def _is_on(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _zone_data(self, status: str) -> dict[str, str]:
        """Files an event under the zone: entity_id is the zone's count
        sensor for `status`, which puts it in a logbook card targeting the
        zone, and device_id puts it in the zone's own Activity (omitted, not
        None, if the device isn't registered)."""
        entity_id = er.async_get(self.hass).async_get_entity_id(
            "sensor", DOMAIN, f"{self._instance.subentry_id}_{status}"
        ) or f"sensor.{self._instance.prefix}flare_{status}"
        # Identifiers are only unique per config entry.
        device = None
        if self.registry_entry is not None and self.registry_entry.config_entry_id is not None:
            identifier = next(iter(self._instance.device_info["identifiers"]))
            device = dr.async_get(self.hass).async_get_device_by_identifier(
                identifier, self.registry_entry.config_entry_id
            )
        return {
            "entity_id": entity_id,
            "zone": self._instance.title,
            **({"device_id": device.id} if device else {}),
        }

    @property
    def native_value(self) -> int:
        return len(self.claims)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"claims": self.claims}


class _ZoneCountSensor(SensorEntity):
    """How many of a zone's lights are in one status. They needn't sum to
    the total: an unavailable light is in neither."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "lights"
    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, registry: ClaimRegistry, instance: ZoneInstance, status: str
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
            async_dispatcher_connect(self.hass, SIGNAL_CLAIMS_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _matching_lights(self) -> tuple[list[str], int]:
        lights: list[str] = []
        records = self._registry.records_for_zone(self._instance.subentry_id)
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

