"""The claim events: what the claims mean as they change, announced on the
bus and filed under FLARE's own entities, so they show in its device's
Activity. Not an entity: sensor.py starts them with the Settings entry."""

from __future__ import annotations

from homeassistant.components.button import ENTITY_ID_FORMAT as BUTTON_ENTITY_ID
from homeassistant.components.sensor import ENTITY_ID_FORMAT as SENSOR_ENTITY_ID
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, EVENT_HOMEASSISTANT_STOP, STATE_ON, Platform
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from ..const import (
    ATTR_CONTROLLED,
    ATTR_LATEST,
    ATTR_LIGHT,
    ATTR_LIGHTS,
    ATTR_LIVE,
    ATTR_LIVE_CONTEXT_ID,
    ATTR_OBSERVED,
    ATTR_PREVIOUS_STATUS,
    ATTR_ROOM,
    ATTR_ROOMS,
    CLEAR_OBJECT_ID,
    CLEAR_ROLE,
    DOMAIN,
    EVENT_LIGHT_OVERRIDDEN,
    EVENT_LIGHTS_CONTROLLED,
    EVENT_LIGHTS_RELEASED,
    NAME,
)
from .claims import SIGNAL_CLAIMS_UPDATED, ClaimRegistry
from .override_protection import MISMATCH_GRACE, LightStatus


def count_object_id(status: LightStatus) -> str:
    return f"flare_{status}_lights"


def classify_tracked(registry: ClaimRegistry, entity_id: str) -> LightStatus:
    """One claimed light's status, shared by every sensor here so they agree."""
    status, _via = registry.status(entity_id)
    # Untracked shows as controlled: either way, not excluded.
    return LightStatus.CONTROLLED if status == LightStatus.UNTRACKED else status


# What the override event carries of the registry's log entry.
_OVERRIDE_EVENT_KEYS = (
    ATTR_LIGHT,
    ATTR_ROOMS,
    ATTR_PREVIOUS_STATUS,
    ATTR_LIVE_CONTEXT_ID,
    ATTR_LIVE,
    ATTR_OBSERVED,
    ATTR_LATEST,
)

# How long a room gathers lights it has taken before announcing them.
CONTROLLED_GATHER_SECONDS = 3


def settings_device_info(entry: ConfigEntry) -> DeviceInfo:
    """FLARE's own device, holding the Settings entry's entities, so their
    events show in its Activity."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)}, name=NAME, entry_type=DeviceEntryType.SERVICE, model="Settings"
    )


def _filed_under(hass: HomeAssistant, entry: ConfigEntry, role: str) -> dict[str, str]:
    """Where an event is filed: entity_id is a count sensor, or Clear for a
    release, which is how the Activity card tells the kinds apart, and
    device_id puts it in FLARE's device's Activity (omitted, not None, if the
    device isn't registered)."""
    domain = Platform.BUTTON if role == CLEAR_ROLE else Platform.SENSOR
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{role}") or (
        BUTTON_ENTITY_ID.format(CLEAR_OBJECT_ID) if role == CLEAR_ROLE else SENSOR_ENTITY_ID.format(count_object_id(role))
    )
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    return {ATTR_ENTITY_ID: entity_id, **({ATTR_DEVICE_ID: device.id} if device else {})}


class ClaimEvents:
    """Announces what the claims mean as they change: fires
    EVENT_LIGHT_OVERRIDDEN when a light becomes overridden, with the claims
    and live values at that moment, EVENT_LIGHTS_CONTROLLED when a room takes
    lights it wasn't setting, and EVENT_LIGHTS_RELEASED when a room lets them
    go. A light becoming controlled again is churn, not news, so it's silent.
    Filed under FLARE's entities so they show in its Activity."""

    def __init__(self, hass: HomeAssistant, registry: ClaimRegistry, entry: ConfigEntry) -> None:
        self.hass = hass
        self._registry = registry
        self._entry = entry
        self._last_statuses: dict[str, str] | None = None
        self._newly_controlled: set[str] = set()
        self._announce_later = None
        self._recheck_later = None

    @callback
    def start(self) -> CALLBACK_TYPE:
        self._registry.register(self)
        # Seeds the statuses, noting any restored claim's mismatch.
        self._refresh_statuses()
        # Nothing unloads the entry at shutdown, so the timers go then too.
        cancel_on_stop = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._cancel_timers)

        @callback
        def stop() -> None:
            self._registry.unregister()
            if not self.hass.is_stopping:
                cancel_on_stop()
            self._cancel_timers()

        return stop

    @callback
    def _cancel_timers(self, _event: Event | None = None) -> None:
        for cancel in (self._announce_later, self._recheck_later):
            if cancel is not None:
                cancel()
        self._announce_later = self._recheck_later = None

    @callback
    def async_claims_changed(self) -> None:
        self._refresh_statuses()

    @callback
    def _refresh_statuses(self) -> None:
        # Also catches a mismatch nothing has noted yet, such as a restored
        # claim's.
        self._registry.note_mismatches()
        statuses = {}
        for entity_id in self._registry.all_records():
            status = classify_tracked(self._registry, entity_id)
            statuses[entity_id] = status
            if status == LightStatus.MISMATCHED:
                self._recheck_after_grace()
            if self._last_statuses is None:
                continue
            previous = self._last_statuses.get(entity_id)
            if status == LightStatus.OVERRIDDEN and previous != LightStatus.OVERRIDDEN:
                self._fire_overridden(entity_id, previous)
            # Not back from overridden (churn), nor from unavailable or
            # mismatched (every light, after a restart), which were already
            # controlled.
            elif status == LightStatus.CONTROLLED and previous not in (
                LightStatus.CONTROLLED,
                LightStatus.OVERRIDDEN,
                LightStatus.UNAVAILABLE,
                LightStatus.MISMATCHED,
            ):
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
        # The sensors settle too.
        async_dispatcher_send(self.hass, SIGNAL_CLAIMS_UPDATED)

    @callback
    def _fire_overridden(self, entity_id: str, previous: str | None) -> None:
        """Logged in the registry too, for the diagnostics."""
        logged = self._registry.log_override(entity_id, previous)
        self.hass.bus.async_fire(
            EVENT_LIGHT_OVERRIDDEN,
            {
                **{key: logged[key] for key in _OVERRIDE_EVENT_KEYS},
                **_filed_under(self.hass, self._entry, LightStatus.OVERRIDDEN),
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
        for key in sorted(self._registry.room_keys()):
            lit = sorted(
                e for e in self._registry.room_lights(key) if statuses.get(e) == LightStatus.CONTROLLED and self._is_on(e)
            )
            lights = [e for e in lit if e in gathered]
            if not lights:
                continue
            self.hass.bus.async_fire(
                EVENT_LIGHTS_CONTROLLED,
                {
                    ATTR_LIGHTS: lights,
                    ATTR_CONTROLLED: len(lit),
                    ATTR_ROOM: self._registry.room_entity_id(key),
                    **_filed_under(self.hass, self._entry, LightStatus.CONTROLLED),
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
                ATTR_LIGHTS: entity_ids,
                ATTR_ROOM: self._registry.room_entity_id(room) if room else None,
                **_filed_under(self.hass, self._entry, CLEAR_ROLE),
            },
        )

    def _is_on(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == STATE_ON
