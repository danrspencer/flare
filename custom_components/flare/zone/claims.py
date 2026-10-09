"""Records which context.id FLARE last wrote each light with, so override
protection can tell our changes from anyone else's. context.id, not
user_id: every call in one automation run shares its run's context,
while another automation's calls don't.

The caller names the zone on every call; with none,
nothing is tracked. Callers naming the same zone share its claims.

Claims live on each zone's claims sensor, a RestoreEntity, so they
survive restarts. A restart gives every light a new context, so
restored claims are matched by value (see classify()).

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
restart."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Optional, Protocol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from homeassistant.util import ulid as ulid_util

from ..const import DOMAIN, SUBENTRY_TYPE_ZONE
from .matching import shown
from .override_protection import (
    MISMATCH_GRACE,
    _context_matches,
    _ContextClaim,
    _WriteRecord,
    classify_state,
    disagrees,
)

# Pruning early is harmless: a light with no record is simply free to
# manage.
STALE_RECORD_MAX_AGE_DAYS = 1

PRUNE_CHECK_INTERVAL = timedelta(hours=1)

# Fired whenever any zone's claims change, so the count sensors refresh.
SIGNAL_CLAIMS_UPDATED = "flare_claims_updated"

# A notification, per light, when a write lands in one zone while another
# holds a claim on the same light. Each zone then reads the other's writes
# as overrides, so the light quietly stops following either.
NOTIFICATION_LIGHT_IN_TWO_ZONES = "flare_light_in_two_zones"


class ClaimStore(Protocol):
    """A zone's claims sensor, as ClaimRegistry needs it. Structural, to
    avoid importing sensor.py circularly."""

    claims: dict[str, _WriteRecord]

    def async_claims_changed(self) -> None:
        """Publish the mutated claims as the entity's own state."""

    def async_announce_released(self, entity_ids: list[str]) -> None:
        """Say the zone let these lights go."""


class ClaimRegistry:
    """Routes each light to the zone that holds its claims. Holds no claims
    itself; they live on each zone's claims sensor."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._stores: dict[str, ClaimStore] = {}
        # Lights already warned about this run, so a dismissed warning stays
        # dismissed rather than returning on the next write.
        self._warned: set[str] = set()
        # Where each light last came back online, tracked or not: its claim
        # was dropped when it went, so the next write may come after.
        self._reconnects: dict[str, datetime] = {}

    def reconnected_at(self, entity_id: str) -> datetime | None:
        """When the light last came back online this run, or None."""
        return self._reconnects.get(entity_id)

    @callback
    def note_mismatch(self, store: ClaimStore, entity_id: str) -> bool:
        """Keeps the record's `mismatch_since`: set when the light first
        stops matching its claims, cleared when it matches again or can't be
        reached. True if it changed."""
        record = store.claims.get(entity_id)
        if record is None:
            return False
        status, _via = classify_state(
            self._hass.states.get(entity_id), record, reconnected_at=self.reconnected_at(entity_id)
        )
        if disagrees(status) and not record.get("mismatch_since"):
            record["mismatch_since"] = dt_util.utcnow().isoformat()
            return True
        if not disagrees(status) and record.pop("mismatch_since", None) is not None:
            return True
        return False

    @callback
    def note_mismatches(self, store: ClaimStore) -> bool:
        """note_mismatch for every light the zone holds. True if any changed."""
        return any([self.note_mismatch(store, entity_id) for entity_id in list(store.claims)])

    @callback
    def register(self, subentry_id: str, store: ClaimStore) -> None:
        self._stores[subentry_id] = store

    @callback
    def unregister(self, subentry_id: str) -> None:
        self._stores.pop(subentry_id, None)

    def resolve_zone_device(self, device_id: str | None) -> str | None:
        """zone_device_id -> subentry_id. None stays None (untracked); a
        device that isn't one of this entry's zones raises."""
        if device_id is None:
            return None
        device = dr.async_get(self._hass).async_get(device_id)
        subentry_id = next(
            (sid for (domain, sid) in (device.identifiers if device else ()) if domain == DOMAIN),
            None,
        )
        subentry = self._entry.subentries.get(subentry_id) if subentry_id else None
        if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_ZONE:
            raise ServiceValidationError(f"{device_id} is not a FLARE zone")
        return subentry_id

    def zone_title(self, subentry_id: str | None) -> str | None:
        if subentry_id is None:
            return None
        subentry = self._entry.subentries.get(subentry_id)
        return subentry.title if subentry is not None else None

    def _store_for(self, entity_id: str) -> ClaimStore | None:
        """The claims sensor holding this light's claims, or None."""
        for store in self._stores.values():
            if entity_id in store.claims:
                return store
        return None

    def record(self, subentry_id: str | None, entity_id: str) -> _WriteRecord | None:
        """This light's claims in that zone, or None if it holds none."""
        if subentry_id is None:
            return None
        store = self._stores.get(subentry_id)
        return store.claims.get(entity_id) if store else None

    def all_records(self) -> dict[str, _WriteRecord]:
        """Every tracked light across every zone."""
        merged: dict[str, _WriteRecord] = {}
        for store in self._stores.values():
            merged.update(store.claims)
        return merged

    def records_for_zone(self, subentry_id: str) -> dict[str, _WriteRecord]:
        store = self._stores.get(subentry_id)
        return dict(store.claims) if store else {}

    @callback
    def _notify(self, stores: Iterable[ClaimStore]) -> None:
        for store in stores:
            store.async_claims_changed()
        async_dispatcher_send(self._hass, SIGNAL_CLAIMS_UPDATED)

    async def async_clear(self, subentry_id: str | None, entity_ids: list[str], *, announce: bool = False) -> None:
        """Discards claims in one zone - behind claims_clear, the escape hatch for
        a light stuck "overridden", and the Clear button, which announces it.
        No-op without a zone or a record."""
        store = self._stores.get(subentry_id)
        if store is None:
            return
        # A list, not any(...pop...): any() short-circuits and would stop popping.
        cleared = [entity_id for entity_id in entity_ids if store.claims.pop(entity_id, None) is not None]
        if cleared:
            if announce:
                store.async_announce_released(sorted(cleared))
            self._notify([store])

    async def async_override(self, subentry_id: str | None, entity_ids: list[str]) -> None:
        """Marks lights as someone else's in one zone - behind claims_override.
        The claim is an `observed` nothing will ever match, by context or by
        value, so the light reads "overridden" until the zone goes dark, its
        claims are cleared, or a forced write takes it back. No-op without a
        zone."""
        store = self._stores.get(subentry_id)
        if store is None or not entity_ids:
            return
        now = dt_util.utcnow().isoformat()
        # Someone said so, so there's nothing to wait for.
        overridden_since = (dt_util.utcnow() - MISMATCH_GRACE).isoformat()
        for entity_id in entity_ids:
            store.claims[entity_id] = {
                "observed": {
                    "context_id": ulid_util.ulid_now(),
                    "secondary_context_id": None,
                    "recorded_at": now,
                    "target": None,
                },
                "latest": None,
                "last_seen": now,
                "mismatch_since": overridden_since,
            }
        self._notify([store])

    @callback
    def adopt(self, subentry_id: str | None, entity_ids: list[str]) -> None:
        """Claims lights that are on and already showing what the caller would
        send, so nothing was written to them: their claim is what they show
        now. Lights claimed in any zone are left alone. No-op without a zone."""
        store = self._stores.get(subentry_id)
        if store is None:
            return
        now = dt_util.utcnow().isoformat()
        adopted = []
        for entity_id in entity_ids:
            state = self._hass.states.get(entity_id)
            if state is None or state.state != "on" or any(entity_id in other.claims for other in self._stores.values()):
                continue
            store.claims[entity_id] = {
                "observed": {
                    "context_id": state.context.id,
                    "secondary_context_id": None,
                    "recorded_at": now,
                    "target": shown(state.attributes),
                },
                "latest": None,
                "last_seen": now,
            }
            adopted.append(entity_id)
        if adopted:
            self._notify([store])

    async def async_record(
        self,
        subentry_id: str | None,
        entity_ids: list[str],
        live_context_before_write: dict[str, str | None],
        context_id: str,
        targets: dict[str, dict] | None = None,
        secondary_context_ids: dict[str, str] | None = None,
        context_id_overrides: dict[str, str] | None = None,
    ) -> None:
        """Records a write for entity_ids, before it's dispatched. Promotes
        `latest` to `observed` if it landed (see the module docstring). A None
        zone records nothing. A light claimed by a different zone keeps that
        claim.

        live_context_before_write: each light's context before this call's
        writes, so it can't reflect the write being recorded.
        targets: what each write asked for.
        secondary_context_ids / context_id_overrides: two-step lights only -
        the brightness and colour steps' contexts."""
        if not entity_ids:
            return
        # Also covers a zone whose claims sensor isn't up yet.
        store = self._stores.get(subentry_id)
        if store is None:
            return
        targets = targets or {}
        secondary_context_ids = secondary_context_ids or {}
        context_id_overrides = context_id_overrides or {}
        for entity_id in entity_ids:
            old = store.claims.get(entity_id)
            observed: Optional[_ContextClaim]
            if old is not None:
                old_latest = old.get("latest")
                if _context_matches(old_latest, live_context_before_write.get(entity_id)):
                    observed = old_latest
                else:
                    observed = old.get("observed")
            else:
                baseline_context = live_context_before_write.get(entity_id)
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
            store.claims[entity_id] = {
                "observed": observed,
                "latest": {
                    "context_id": context_id_overrides.get(entity_id, context_id),
                    "secondary_context_id": secondary_context_ids.get(entity_id),
                    "recorded_at": dt_util.utcnow().isoformat(),
                    "target": targets.get(entity_id),
                },
                "last_seen": dt_util.utcnow().isoformat(),
            }
            # A new write starts afresh: a mismatch now is the write landing.
            self.note_mismatch(store, entity_id)
        self._notify([store])
        for entity_id in entity_ids:
            others = [sid for sid, other in self._stores.items() if sid != subentry_id and entity_id in other.claims]
            if others:
                self._warn_light_in_two_zones(entity_id, [subentry_id, *others])

    @callback
    def _warn_light_in_two_zones(self, entity_id: str, subentry_ids: list[str]) -> None:
        """Once per light per run. Notifications don't survive a restart, so
        a conflict that's been fixed is never warned about again."""
        if entity_id in self._warned:
            return
        self._warned.add(entity_id)
        state = self._hass.states.get(entity_id)
        light = state.name if state is not None else entity_id
        zones = sorted(self.zone_title(sid) or sid for sid in subentry_ids)
        persistent_notification.async_create(
            self._hass,
            f"**{light}** (`{entity_id}`) is being driven in the "
            f"{', '.join(zones[:-1])} and {zones[-1]} zones. Each zone treats the other's "
            "changes as someone overriding the light, so it can stop following its schedule.\n\n"
            "Give each light one zone. If two blueprint automations both include it, pick the "
            "same Zone in both, or take the light out of one of them.",
            title=f"FLARE: {light} is in more than one zone",
            notification_id=f"{NOTIFICATION_LIGHT_IN_TWO_ZONES}_{entity_id}",
        )

    async def async_prune_stale(self) -> None:
        """Discards records untouched for STALE_RECORD_MAX_AGE_DAYS: the only
        cleanup an entity deleted from HA ever gets. A record with no parseable
        `last_seen` is kept."""
        cutoff = dt_util.utcnow() - timedelta(days=STALE_RECORD_MAX_AGE_DAYS)
        stale = []
        for entity_id, record in self.all_records().items():
            last_seen = record.get("last_seen")
            if not last_seen:
                continue
            parsed = dt_util.parse_datetime(last_seen)
            if parsed is not None and parsed < cutoff:
                stale.append(entity_id)
        if not stale:
            return
        touched: set[int] = set()
        stores = []
        for entity_id in stale:
            store = self._store_for(entity_id)
            if store is None:
                continue
            store.claims.pop(entity_id, None)
            if id(store) not in touched:
                touched.add(id(store))
                stores.append(store)
        if stores:
            self._notify(stores)

    @callback
    def _release_if_dark(self, store: ClaimStore) -> None:
        """Discards a zone's claims once none of its lights are on. Switching a
        light off is an override, so this is what hands it back. Unavailable
        counts as dark, so one dead entity can't block the release."""
        if not store.claims:
            return
        for entity_id in store.claims:
            state = self._hass.states.get(entity_id)
            if state is not None and state.state == "on":
                return
        released = sorted(store.claims)
        store.claims.clear()
        store.async_announce_released(released)

    def async_start_listening(self, hass: HomeAssistant) -> CALLBACK_TYPE:
        """One listener for every tracked light:

        - Back online (unavailable/unknown -> on/off), any light:
          noted for classify_state, tracked or not, since a claim may come
          after it. Forgotten once a write from FLARE is seen landing.
        - Any change to a tracked light: its `mismatch_since` kept.
        - Drop (on/off -> unavailable/unknown): clears the light's claim.
        - Off (on/off -> off): releases the zone if it has gone dark."""
        reconnects = self._reconnects

        @callback
        def _on_state_changed(event: Event[EventStateChangedData]) -> None:
            entity_id = event.data["entity_id"]
            old, new = event.data["old_state"], event.data["new_state"]
            if (
                entity_id.startswith("light.")
                and new is not None
                and new.state in ("on", "off")
                and old is not None
                and old.state in ("unavailable", "unknown")
            ):
                reconnects[entity_id] = new.last_changed
            store = self._store_for(entity_id)
            if store is None or entity_id not in store.claims:
                return
            if new is not None and _context_matches(store.claims[entity_id].get("latest"), new.context.id):
                # FLARE's write landed: the light has settled under FLARE.
                reconnects.pop(entity_id, None)
            old_available = old is not None and old.state not in ("unavailable", "unknown")
            # Explicitly unavailable, not removed: every entity is removed across a
            # restart.
            new_explicitly_unavailable = new is not None and new.state in ("unavailable", "unknown")
            dropped = old_available and new_explicitly_unavailable
            # Not unknown -> off, which is a light reconnecting.
            went_off = old_available and new is not None and new.state == "off"

            if dropped:
                store.claims.pop(entity_id, None)
            changed = self.note_mismatch(store, entity_id)
            if dropped or went_off:
                self._release_if_dark(store)
            if dropped or went_off or changed:
                self._notify([store])

        return hass.bus.async_listen("state_changed", _on_state_changed)
