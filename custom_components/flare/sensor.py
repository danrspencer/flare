"""Sensor platform for both entries.

Schedules: sensor.<name>_flare per schedule. State is the phase; the
attributes carry the current brightness/color_temp/rgb_color, today's
boundaries, and the full-day `points` curve.

Settings: the sensor holding every claim and room, plus
`controlled`/`overridden` counts, and a status sensor for each room light,
on the light's own device."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_SETTINGS,
    EVENT_LIGHT_OVERRIDDEN,
    EVENT_LIGHTS_CONTROLLED,
    EVENT_LIGHTS_RELEASED,
)
from .schedule.coordinator import ScheduleCoordinator, ScheduleInstance, schedule_instances
from .tracking.matching import shown
from .tracking.override_protection import MISMATCH_GRACE, classify_state
from .tracking.claims import SIGNAL_CLAIMS_UPDATED, ClaimRegistry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_SETTINGS:
        for instance in schedule_instances(entry):
            coordinator: ScheduleCoordinator = hass.data[DOMAIN][instance.subentry_id]
            async_add_entities([_ScheduleSensor(coordinator, instance)], config_subentry_id=instance.subentry_id)
        return

    registry: ClaimRegistry = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            _ClaimsSensor(hass, registry, entry),
            *(_CountSensor(hass, registry, entry, status) for status in ("controlled", "overridden")),
        ]
    )
    _LightStatuses(hass, registry, entry, async_add_entities).start()


def _classify_tracked(
    hass: HomeAssistant, registry: ClaimRegistry, entity_id: str, record: dict
) -> tuple[str, Any, Any]:
    """One light's status, shared by every sensor here so they agree.
    Returns (status, matched_via, live_context_id)."""
    state = hass.states.get(entity_id)
    live_context_id = state.context.id if state is not None else None
    raw_status, matched_via = classify_state(state, record, reconnected_at=registry.reconnected_at(entity_id))
    # "untracked" shows as "controlled": either way, not excluded.
    return ("controlled" if raw_status == "untracked" else raw_status), matched_via, live_context_id


# How long a room gathers lights it has taken before announcing them.
CONTROLLED_GATHER_SECONDS = 3


def settings_device_info(entry: ConfigEntry) -> DeviceInfo:
    """FLARE's own device, holding the Settings entry's entities, so their
    events show in its Activity."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)}, name="FLARE", entry_type=DeviceEntryType.SERVICE, model="Settings"
    )


def _filed_under(hass: HomeAssistant, entry: ConfigEntry, role: str) -> dict[str, str]:
    """Where an event is filed: entity_id is a count sensor, or Clear for a
    release, which is how the Activity card tells the kinds apart, and
    device_id puts it in FLARE's device's Activity (omitted, not None, if the
    device isn't registered)."""
    domain = "button" if role == "clear" else "sensor"
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{role}") or (
        "button.flare_clear" if role == "clear" else f"sensor.flare_{role}_lights"
    )
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    return {"entity_id": entity_id, **({"device_id": device.id} if device else {})}


class _ClaimsSensor(SensorEntity, RestoreEntity):
    """Every claim and room - the storage itself, published as attributes,
    with each claimed light's status for the dashboard. Kept out of the
    recorder but restored across a restart."""

    _attr_has_entity_name = False
    _attr_name = "FLARE claims"
    _attr_icon = "mdi:text-search"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "lights"
    # Polls too, since claims are judged against live state that changes
    # without any claim changing.
    _unrecorded_attributes = frozenset({"claims", "rooms", "statuses"})

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, entry: ConfigEntry) -> None:
        self.hass = hass
        self._registry = registry
        self._entry = entry
        self.claims: dict[str, dict] = {}
        self.rooms: dict[str, dict] = {}
        self._last_statuses: dict[str, str] | None = None
        self._newly_controlled: set[str] = set()
        self._announce_later = None
        self._recheck_later = None
        self._attr_unique_id = f"{entry.entry_id}_claims"
        self._attr_translation_key = "claims"
        self.entity_id = "sensor.flare_claims"
        self._attr_device_info = settings_device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restored before registering, so no write lands in a dict about to be
        # replaced.
        last = await self.async_get_last_extra_data()
        if last is not None:
            data = last.as_dict()
            self.claims = dict(data.get("claims") or {})
            self.rooms = dict(data.get("rooms") or {})
        self._registry.register(self)
        # Lights already reporting dark won't change again to release them.
        self._registry.release_settled_dark_rooms()
        # The setup-time prune ran before this entity existed.
        await self._registry.async_prune_stale()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return RestoredExtraData({"claims": self.claims, "rooms": self.rooms})

    async def async_will_remove_from_hass(self) -> None:
        self._registry.unregister()
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
        when a room takes lights it wasn't setting. A light becoming
        controlled again is churn, not news, so it's silent. Not in
        extra_state_attributes, which HA reads on every state write."""
        # Also catches a mismatch nothing has noted yet, such as a restored
        # claim's.
        self._registry.note_mismatches()
        statuses = {}
        for entity_id, record in self.claims.items():
            status, _via, live_context_id = _classify_tracked(self.hass, self._registry, entity_id, record)
            statuses[entity_id] = status
            if status == "mismatched":
                self._recheck_after_grace()
            if self._last_statuses is None:
                continue
            previous = self._last_statuses.get(entity_id)
            if status == "overridden" and previous != "overridden":
                self._fire_overridden(entity_id, record, previous, live_context_id)
            # Not back from overridden (churn), nor from unavailable or
            # mismatched (every light, after a restart), which were already
            # controlled.
            elif status == "controlled" and previous not in ("controlled", "overridden", "unavailable", "mismatched"):
                self._controlled_soon(entity_id)
        # The first pass seeds without firing, so a restart doesn't re-announce.
        self._last_statuses = statuses

    @callback
    def _recheck_after_grace(self) -> None:
        if self._recheck_later is None:
            self._recheck_later = async_call_later(
                self.hass, MISMATCH_GRACE.total_seconds() + 1, self._recheck
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
                "rooms": [self._registry.room_entity_id(key) for key in self._registry.rooms_of(entity_id)],
                **_filed_under(self.hass, self._entry, "overridden"),
                "previous_status": previous,
                "live_context_id": live_context_id,
                "live": {"state": state.state, **shown(state.attributes)} if state else {"state": None},
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
        """One event per room. Only lights that are on: a turn-off claims
        lights too, and taking a room's lights to switch them off isn't
        taking control of them."""
        self._announce_later = None
        gathered, self._newly_controlled = self._newly_controlled, set()
        statuses = self._last_statuses or {}
        for key, room in sorted(self.rooms.items()):
            lit = sorted(
                e for e in room.get("lights", ()) if statuses.get(e) == "controlled" and self._is_on(e)
            )
            lights = [e for e in lit if e in gathered]
            if not lights:
                continue
            self.hass.bus.async_fire(
                EVENT_LIGHTS_CONTROLLED,
                {
                    "lights": lights,
                    "controlled": len(lit),
                    "room": self._registry.room_entity_id(key),
                    **_filed_under(self.hass, self._entry, "controlled"),
                },
            )

    @callback
    def async_announce_released(self, room: str | None, entity_ids: list[str]) -> None:
        """A room let these go: dark, or Clear."""
        if not entity_ids:
            return
        self.hass.bus.async_fire(
            EVENT_LIGHTS_RELEASED,
            {
                "lights": entity_ids,
                "room": self._registry.room_entity_id(room) if room else None,
                **_filed_under(self.hass, self._entry, "clear"),
            },
        )

    def _is_on(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    @property
    def native_value(self) -> int:
        return len(self.claims)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Copies: the registry mutates these dicts in place, and a published
        # state sharing them would change with it, so the frontend's diff
        # against the last state would never see a change.
        return {
            "claims": copy.deepcopy(self.claims),
            "rooms": copy.deepcopy(self.rooms),
            "statuses": dict(self._last_statuses or {}),
        }


class _CountSensor(SensorEntity):
    """How many claimed lights are in one status. They needn't sum to the
    total: an unavailable light is in neither."""

    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "lights"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, entry: ConfigEntry, status: str) -> None:
        self.hass = hass
        self._registry = registry
        self._status = status
        self._attr_icon = "mdi:lightbulb-group" if status == "controlled" else "mdi:lightbulb-alert-outline"
        self._attr_unique_id = f"{entry.entry_id}_{status}"
        self._attr_translation_key = f"all_{status}"
        self.entity_id = f"sensor.flare_{status}_lights"
        self._attr_name = f"FLARE {status} lights"
        self._attr_device_info = settings_device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CLAIMS_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _matching_lights(self) -> tuple[list[str], int]:
        lights: list[str] = []
        records = self._registry.all_records()
        for entity_id, record in records.items():
            status, _via, _ctx = _classify_tracked(self.hass, self._registry, entity_id, record)
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


# What a light's status sensor can say; an unreachable light makes it
# unavailable instead.
LIGHT_STATUSES = ("controlled", "overridden", "mismatched", "untracked", "off")
STATUS_UNIQUE_ID = "{entry_id}_status_{light}"


class _LightStatuses:
    """A status sensor for every light some room has named, added as each
    first appears and kept after, so its history carries on. Keyed by the
    light's registry id (its entity_id if it has none), so a rename keeps
    it. Removed with the light."""

    def __init__(
        self, hass: HomeAssistant, registry: ClaimRegistry, entry: ConfigEntry, add: AddEntitiesCallback
    ) -> None:
        self._hass = hass
        self._registry = registry
        self._entry = entry
        self._add = add
        # Light key -> its sensor.
        self._sensors: dict[str, _LightStatusSensor] = {}

    def start(self) -> None:
        prefix = STATUS_UNIQUE_ID.format(entry_id=self._entry.entry_id, light="")
        known = [
            e.unique_id[len(prefix) :]
            for e in er.async_entries_for_config_entry(er.async_get(self._hass), self._entry.entry_id)
            if e.unique_id.startswith(prefix)
        ]
        self._add_for(known)
        self._entry.async_on_unload(async_dispatcher_connect(self._hass, SIGNAL_CLAIMS_UPDATED, self._claims_changed))
        self._entry.async_on_unload(
            self._hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_updated)
        )

    def _key(self, entity_id: str) -> str:
        entry = er.async_get(self._hass).async_get(entity_id)
        return entry.id if entry is not None else entity_id

    @callback
    def _add_for(self, keys) -> None:
        new = [_LightStatusSensor(self._hass, self._registry, self._entry, key) for key in keys if key not in self._sensors]
        for sensor in new:
            self._sensors[sensor.light_key] = sensor
        if new:
            self._add(new)

    @callback
    def _claims_changed(self) -> None:
        lights = set(self._registry.all_records())
        for key in self._registry.room_keys():
            lights.update(self._registry.room_lights(key))
        self._add_for(sorted({self._key(entity_id) for entity_id in lights}))

    @callback
    def _registry_updated(self, event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        if event.data["action"] != "remove" or not event.data["entity_id"].startswith("light."):
            return
        # The light's registry entry is gone, so it's keyed by the id the
        # sensor remembered.
        for key, sensor in list(self._sensors.items()):
            if sensor.light_entity_id == event.data["entity_id"]:
                del self._sensors[key]
                if sensor.registry_entry is not None:
                    er.async_get(self._hass).async_remove(sensor.entity_id)


class _LightStatusSensor(SensorEntity):
    """What FLARE makes of one light, as claims_check says it, on the light's
    own device so its page shows it. Untracked is FLARE holding nothing on
    it. Unavailable while the light is."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(LIGHT_STATUSES)
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "status"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, entry: ConfigEntry, key: str) -> None:
        self.hass = hass
        self._registry = registry
        self.light_key = key
        self._attr_unique_id = STATUS_UNIQUE_ID.format(entry_id=entry.entry_id, light=key)
        light = er.async_get(hass).async_get(key)
        self.light_entity_id = light.entity_id if light is not None else key
        device = dr.async_get(hass).async_get(light.device_id) if light and light.device_id else None
        if device is not None:
            # The light's device itself, as HA's own helpers link to their
            # source's: device info would register a device of FLARE's own,
            # since identifiers are unique per config entry.
            self._attr_has_entity_name = True
            self.device_entry = device
        else:
            state = hass.states.get(self.light_entity_id)
            self._attr_has_entity_name = False
            self._attr_name = f"{state.name if state else self.light_entity_id} FLARE status"
        self.entity_id = f"sensor.{self.light_entity_id.split('.', 1)[1]}_flare_status"
        self._unsubscribe_light = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_CLAIMS_UPDATED, self._handle_update))
        self.async_on_remove(self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._light_renamed))
        self.async_on_remove(self._stop_following)
        self._follow_light()

    @callback
    def _stop_following(self) -> None:
        if self._unsubscribe_light is not None:
            self._unsubscribe_light()
            self._unsubscribe_light = None

    @callback
    def _follow_light(self) -> None:
        if self._unsubscribe_light is not None:
            self._unsubscribe_light()
        self._unsubscribe_light = async_track_state_change_event(
            self.hass, [self.light_entity_id], self._light_changed
        )

    @callback
    def _light_changed(self, _event: Event) -> None:
        self.async_write_ha_state()

    @callback
    def _light_renamed(self, event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        if event.data["action"] == "update" and event.data.get("old_entity_id") == self.light_entity_id:
            self.light_entity_id = event.data["entity_id"]
            self._follow_light()
            self._handle_update()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _status(self) -> str:
        status, _via = classify_state(
            self.hass.states.get(self.light_entity_id),
            self._registry.record(self.light_entity_id),
            reconnected_at=self._registry.reconnected_at(self.light_entity_id),
        )
        return status

    @property
    def available(self) -> bool:
        return self._status() != "unavailable"

    @property
    def native_value(self) -> str | None:
        status = self._status()
        return status if status in LIGHT_STATUSES else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "light": self.light_entity_id,
            "rooms": [self._registry.room_entity_id(key) for key in self._registry.rooms_of(self.light_entity_id)],
        }


class _ScheduleSensor(CoordinatorEntity[ScheduleCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:home-lightbulb"
    _attr_name = None  # the entity that represents the device - displays as just the device's own name
    # Over the recorder's attribute size limit, and only read live.
    _unrecorded_attributes = frozenset({"points"})

    def __init__(self, coordinator: ScheduleCoordinator, instance: ScheduleInstance) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{instance.subentry_id}_flare"
        self._attr_translation_key = "schedule"
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

