"""Records which context.id FLARE last wrote each light with, so override
protection can tell our changes from anyone else's. context.id, not
user_id: every call in one automation run shares its run's context,
while another automation's calls don't.

Claims are FLARE's, one per light, whoever made the write. A caller
tracks its writes by naming a room (`room_id`, usually its automation)
and the room's lights; with no room, nothing is tracked. A room's claims
are released once none of its claimed lights is on.

Claims and rooms live here, saved to HA's storage (`.storage/flare.claims`)
moments after each change, so they survive restarts. A restart gives every
light a new context, so restored claims are matched by value (see
classify()). What they say is shown through each light's status sensor.

Two claims per light
--------------------
- `observed`: a state we've seen and can safely write over - a write
  seen landing, or for a first-ever write, the context from just before.
- `latest`: our most recent write, not yet seen landing.

Claims are recorded before dispatch. On the next write, if the light's
context matches `latest`, it's promoted to `observed`; if it still
matches `observed`, `latest` never landed and `observed` stays. Either
way the light is still ours, so a dropped write can't lock it out.

HA forgets a write's context after 5s, so a slow device can echo our
write under a new context. Each claim therefore records its `target`,
and classify() also compares values.

Listener rules
--------------
A light dropping from on/off to unavailable/unknown loses its claim, so
its reconnect isn't mistaken for an override. There's deliberately no
re-baseline on reconnect: after a restart it would mark every restored
override as ours. Both listener rules require a real on/off starting
state, since nearly every light passes through unavailable/unknown on
restart. Nothing a light reports while HA is stopping counts.

A claimed light's registry entry is followed too: its claim moves with a
rename and goes when the light is deleted."""

from __future__ import annotations

from typing import Optional, Protocol

from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_entity_registry_updated_event,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import ulid as ulid_util

from ..const import DEFAULT_MIN_BRIGHTNESS_CHANGE, DEFAULT_MIN_COLOR_TEMP_CHANGE, is_reachable
from .matching import shown
from .override_protection import (
    MISMATCH_GRACE,
    _context_matches,
    _ContextClaim,
    _WriteRecord,
    classify_state,
    disagrees,
)

# Fired whenever the claims change, so the sensors refresh.
SIGNAL_CLAIMS_UPDATED = "flare_claims_updated"

STORAGE_KEY = "flare.claims"
STORAGE_VERSION = 1
# Seconds a change waits to be saved, so a room's writes are saved together.
SAVE_DELAY = 5


class ClaimListener(Protocol):
    """What announces claim changes (sensor.py's ClaimEvents). Structural,
    to avoid importing sensor.py circularly."""

    def async_claims_changed(self) -> None:
        """The claims changed."""

    def async_announce_released(self, room: str | None, entity_ids: list[str]) -> None:
        """Say the room let these lights go."""


class ClaimRegistry:
    """Every claim and room, and the rules for keeping them."""

    def __init__(
        self,
        hass: HomeAssistant,
        min_brightness_change: float = DEFAULT_MIN_BRIGHTNESS_CHANGE,
        min_color_temp_change: float = DEFAULT_MIN_COLOR_TEMP_CHANGE,
    ) -> None:
        self._hass = hass
        # The Settings entry's options; a change to them reloads the entry.
        self.min_brightness_change = min_brightness_change
        self.min_color_temp_change = min_color_temp_change
        self.claims: dict[str, _WriteRecord] = {}
        # Room key -> {"lights": [...]}.
        self.rooms: dict[str, dict] = {}
        self._storage: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._listener: ClaimListener | None = None
        # The state and registry listeners, while listening, and the lights
        # they follow: exactly the claimed ones (_retrack).
        self._on_change = None
        self._on_registry_change = None
        self._tracked: frozenset[str] = frozenset()
        self._untrack: list[CALLBACK_TYPE] = []

    async def async_load(self) -> None:
        """The claims and rooms from before the restart."""
        data = await self._storage.async_load() or {}
        self.claims = dict(data.get("claims") or {})
        self.rooms = dict(data.get("rooms") or {})

    @callback
    def _save(self) -> None:
        self._storage.async_delay_save(lambda: {"claims": self.claims, "rooms": self.rooms}, SAVE_DELAY)

    @callback
    def register(self, listener: ClaimListener) -> None:
        self._listener = listener

    @callback
    def unregister(self) -> None:
        self._listener = None

    def room_key(self, room_id: str | None) -> str | None:
        """A room's key: an entity's registry id, which survives a rename, else
        the room_id as given. None stays None (untracked)."""
        if not room_id:
            return None
        entry = er.async_get(self._hass).async_get(room_id)
        return entry.id if entry is not None else room_id

    def room_entity_id(self, key: str) -> str:
        """The entity a room is keyed by, as its current entity_id, else the key."""
        entry = er.async_get(self._hass).async_get(key)
        return entry.entity_id if entry is not None else key

    def record(self, entity_id: str) -> _WriteRecord | None:
        """This light's claims, or None if it has none."""
        return self.claims.get(entity_id)

    def status(self, entity_id: str, **tolerances: int) -> tuple[str, str | None]:
        """classify_state for one light: its live state against its claims."""
        return classify_state(
            self._hass.states.get(entity_id),
            self.record(entity_id),
            min_brightness_change=self.min_brightness_change,
            min_color_temp_change=self.min_color_temp_change,
            **tolerances,
        )

    def all_records(self) -> dict[str, _WriteRecord]:
        return dict(self.claims)

    def room_keys(self) -> list[str]:
        return list(self.rooms)

    def room_lights(self, key: str) -> list[str]:
        """Every light a room has named."""
        return list(self.rooms.get(key, {}).get("lights", ()))

    def rooms_of(self, entity_id: str) -> list[str]:
        """Every room this light is one of, by key, sorted."""
        return sorted(key for key, room in self.rooms.items() if entity_id in room.get("lights", ()))

    @callback
    def note_mismatch(self, entity_id: str) -> bool:
        """Keeps the record's `mismatch_since`: set when the light first
        stops matching its claims, cleared when it matches again or can't be
        reached. True if it changed."""
        record = self.record(entity_id)
        if record is None:
            return False
        status, _via = self.status(entity_id)
        if disagrees(status) and not record.get("mismatch_since"):
            record["mismatch_since"] = dt_util.utcnow().isoformat()
        elif disagrees(status) or record.pop("mismatch_since", None) is None:
            return False
        self._save()
        return True

    @callback
    def note_mismatches(self) -> bool:
        """note_mismatch for every claimed light. True if any changed."""
        return any([self.note_mismatch(entity_id) for entity_id in list(self.claims)])

    @callback
    def _notify(self) -> None:
        self._save()
        self._retrack()
        if self._listener is not None:
            self._listener.async_claims_changed()
        async_dispatcher_send(self._hass, SIGNAL_CLAIMS_UPDATED)

    @callback
    def _retrack(self) -> None:
        """Follows exactly the claimed lights, once the set has changed."""
        lights = frozenset(self.claims)
        if self._on_change is None or lights == self._tracked:
            return
        self._stop_tracking()
        self._tracked = lights
        if lights:
            self._untrack = [
                async_track_state_change_event(self._hass, sorted(lights), self._on_change),
                async_track_entity_registry_updated_event(self._hass, sorted(lights), self._on_registry_change),
            ]

    @callback
    def _stop_tracking(self) -> None:
        for untrack in self._untrack:
            untrack()
        self._untrack, self._tracked = [], frozenset()

    @callback
    def _join(self, key: str | None, written: list[str], room_entities: list[str] | None) -> None:
        """Remembers a room's lights: as its latest write named them, plus
        what it just wrote and any light it still holds a claim on, so every
        claim it made can be released with it."""
        if key is None:
            return
        held = [e for e in self.rooms.get(key, {}).get("lights", ()) if e in self.claims]
        lights = set(room_entities or ()) | set(written) | set(held)
        self.rooms[key] = {"lights": sorted(lights)}

    @callback
    def async_clear(self, entity_ids: list[str], *, announce: bool = False) -> list[str]:
        """Discards claims - behind claims_clear, the escape hatch for a light
        stuck "overridden", and the Clear button, which announces it, once per
        room. Returns what was cleared."""
        rooms = {entity_id: self.rooms_of(entity_id) for entity_id in entity_ids}
        # A list, not any(...pop...): any() short-circuits and would stop popping.
        cleared = [entity_id for entity_id in entity_ids if self.claims.pop(entity_id, None) is not None]
        if cleared and announce:
            by_room: dict[str | None, list[str]] = {}
            for entity_id in cleared:
                # Under its first room, so each light is announced once.
                by_room.setdefault(next(iter(rooms[entity_id]), None), []).append(entity_id)
            for key, lights in sorted(by_room.items(), key=lambda item: item[0] or ""):
                self._announce_released(key, sorted(lights))
        if cleared:
            self._notify()
        return cleared

    @callback
    def async_override(self, room_id: str | None, entity_ids: list[str], room_entities: list[str] | None = None) -> None:
        """Marks lights as someone else's - behind claims_override. The claim
        is an `observed` nothing will ever match, by context or by value, so
        the light reads "overridden" until its room goes dark, its claim is
        cleared, or a forced write takes it back."""
        if not entity_ids:
            return
        key = self.room_key(room_id)
        now = dt_util.utcnow().isoformat()
        # Someone said so, so there's nothing to wait for.
        overridden_since = (dt_util.utcnow() - MISMATCH_GRACE).isoformat()
        for entity_id in entity_ids:
            self.claims[entity_id] = {
                "observed": {
                    "context_id": ulid_util.ulid_now(),
                    "secondary_context_id": None,
                    "recorded_at": now,
                    "target": None,
                },
                "latest": None,
                "mismatch_since": overridden_since,
            }
        self._join(key, entity_ids, room_entities)
        self._notify()

    @callback
    def adopt(self, room_id: str | None, entity_ids: list[str], room_entities: list[str] | None = None) -> None:
        """Claims lights that are on and already showing what the caller would
        send, so nothing was written to them: their claim is what they show
        now. Claimed lights are left alone. No-op without a room."""
        key = self.room_key(room_id)
        if key is None:
            return
        now = dt_util.utcnow().isoformat()
        adopted = []
        for entity_id in entity_ids:
            state = self._hass.states.get(entity_id)
            if state is None or state.state != "on" or entity_id in self.claims:
                continue
            self.claims[entity_id] = {
                "observed": {
                    "context_id": state.context.id,
                    "secondary_context_id": None,
                    "recorded_at": now,
                    "target": shown(state.attributes),
                },
                "latest": None,
            }
            adopted.append(entity_id)
        if adopted:
            self._join(key, adopted, room_entities)
            self._notify()

    @callback
    def async_record(
        self,
        room_id: str | None,
        entity_ids: list[str],
        context_id: str,
        targets: dict[str, dict] | None = None,
        secondary_context_ids: dict[str, str] | None = None,
        context_id_overrides: dict[str, str] | None = None,
        room_entities: list[str] | None = None,
    ) -> None:
        """Records a write for entity_ids, before it's dispatched. Promotes
        `latest` to `observed` if it landed (see the module docstring). A None
        room records nothing. Each light's live context is read here, before
        the write it's recording is dispatched.

        targets: what each write asked for.
        secondary_context_ids / context_id_overrides: two-step lights only -
        the brightness and colour steps' contexts.
        room_entities: the room's lights, which it releases together."""
        key = self.room_key(room_id)
        if not entity_ids or key is None:
            return
        claims = self.claims
        targets = targets or {}
        secondary_context_ids = secondary_context_ids or {}
        context_id_overrides = context_id_overrides or {}
        for entity_id in entity_ids:
            state = self._hass.states.get(entity_id)
            live_context = state.context.id if state is not None else None
            old = claims.get(entity_id)
            observed: Optional[_ContextClaim]
            if old is not None:
                old_latest = old.get("latest")
                if _context_matches(old_latest, live_context):
                    observed = old_latest
                else:
                    observed = old.get("observed")
            else:
                baseline_context = live_context
                observed = (
                    {
                        "context_id": baseline_context,
                        "secondary_context_id": None,
                        "recorded_at": None,
                        "target": None,
                    }
                    if baseline_context is not None
                    else None
                )
            claims[entity_id] = {
                "observed": observed,
                "latest": {
                    "context_id": context_id_overrides.get(entity_id, context_id),
                    "secondary_context_id": secondary_context_ids.get(entity_id),
                    "recorded_at": dt_util.utcnow().isoformat(),
                    "target": targets.get(entity_id),
                },
            }
            # A new write starts afresh: a mismatch now is the write landing.
            self.note_mismatch(entity_id)
        self._join(key, entity_ids, room_entities)
        self._notify()

    def _claimed_lights(self, key: str) -> list[str]:
        lights = self.rooms.get(key, {}).get("lights", ())
        return [entity_id for entity_id in lights if entity_id in self.claims]

    @callback
    def _release_if_dark(self, key: str) -> bool:
        """Discards a room's claims once none of its claimed lights is on.
        Switching a light off is an override, so this is what hands it back.
        Unavailable counts as dark, so one dead entity can't block the
        release. True if it released anything."""
        claimed = self._claimed_lights(key)
        if not claimed:
            return False
        for entity_id in claimed:
            state = self._hass.states.get(entity_id)
            if state is not None and state.state == "on":
                return False
        for entity_id in claimed:
            self.claims.pop(entity_id, None)
        self._announce_released(key, sorted(claimed))
        return True

    @callback
    def _announce_released(self, key: str | None, entity_ids: list[str]) -> None:
        if self._listener is not None:
            self._listener.async_announce_released(key, entity_ids)

    @callback
    def _release_if_settled_dark(self, key: str) -> bool:
        """_release_if_dark for claims that came back from storage (a
        restart, a restore): its lights may have gone off while HA wasn't
        watching, so no on -> off ever reaches the listener. Only once every
        claimed light has reported on or off, so a room isn't released while
        its lights reconnect one at a time."""
        if all(is_reachable(self._hass.states.get(entity_id)) for entity_id in self._claimed_lights(key)):
            return self._release_if_dark(key)
        return False

    @callback
    def release_settled_dark_rooms(self) -> None:
        """_release_if_settled_dark for every room, when the claims come back."""
        if any([self._release_if_settled_dark(key) for key in list(self.rooms)]):
            self._notify()

    def async_start_listening(self) -> CALLBACK_TYPE:
        """Listeners for the claimed lights, re-subscribed as they change.
        Their states:

        - Any change to a tracked light: its `mismatch_since` kept.
        - Drop (on/off -> unavailable/unknown): clears the light's claim.
        - Off (on/off -> off): releases each of its rooms that has gone dark.
        - Arrival (none/unavailable/unknown -> on/off): releases each of its
          rooms whose claimed lights have all now reported and none is on.

        Their registry entries: a rename moves the claim and the light's place
        in its rooms; a deletion drops both."""
        hass = self._hass

        @callback
        def _on_state_changed(event: Event[EventStateChangedData]) -> None:
            entity_id = event.data["entity_id"]
            # MQTT marks its lights unavailable as its connection closes at
            # shutdown, which would drop every claim just before the final save.
            if hass.is_stopping:
                return
            if entity_id not in self.claims:
                return
            old, new = event.data["old_state"], event.data["new_state"]
            old_available = is_reachable(old)
            # Explicitly unavailable, not removed: every entity is removed across a
            # restart.
            new_explicitly_unavailable = new is not None and not is_reachable(new)
            dropped = old_available and new_explicitly_unavailable
            # Not unknown -> off, which is a light reconnecting.
            went_off = old_available and new is not None and new.state == "off"
            arrived = not old_available and is_reachable(new)

            rooms = self.rooms_of(entity_id)
            if dropped:
                self.claims.pop(entity_id, None)
            changed = self.note_mismatch(entity_id)
            if dropped or went_off:
                for key in rooms:
                    self._release_if_dark(key)
            elif arrived:
                for key in rooms:
                    self._release_if_settled_dark(key)
            if dropped or went_off or arrived or changed:
                self._notify()

        @callback
        def _on_registry_changed(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
            data = event.data
            if data["action"] == "remove":
                old, new = data["entity_id"], None
            elif data["action"] == "update" and "old_entity_id" in data:
                old, new = data["old_entity_id"], data["entity_id"]
            else:
                return
            record = self.claims.pop(old, None)
            if record is not None and new is not None:
                self.claims[new] = record
            for room in self.rooms.values():
                if old in room["lights"]:
                    room["lights"] = sorted((set(room["lights"]) - {old}) | ({new} if new else set()))
            self._notify()

        self._on_change = _on_state_changed
        self._on_registry_change = _on_registry_changed
        self._retrack()

        @callback
        def _stop() -> None:
            self._on_change = self._on_registry_change = None
            self._stop_tracking()

        return _stop
