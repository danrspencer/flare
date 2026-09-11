"""
Tracks which context.id this integration last wrote each light with, so
grouping.py can tell "did WE make the last change" apart from a person,
another automation, or a device reconnecting under its own fresh
context.

context.id rather than context.user_id: every service call within one
automation run shares that run's context.id (HA core's
helpers/script.py passes Script._context to every action step), while
anything else - including a different automation - gets an unrelated
one. user_id can't distinguish our own write from another automation's,
since neither carries one.

A claim's scope is supplied by the caller, not discovered from the
entity_id - every read/write method below takes a subentry_id
identifying which state device to act on. `resolve_scope_device()`
turns a device_id (what a service call actually receives) into that
subentry_id; passing none means "don't track this write at all", not
"go find out where it belongs" - see its own docstring. Two automations
that pass the *same* scope for one light share its claims and
co-operate rather than each reading the other as an intruder; two that
pass different scopes are asking to be tracked apart, and are.

A state device's own `target` (coordinator.py's `StateInstance.target`)
plays no part in any of this - it only seeds where the device's own
entry lands in the Area registry (sensor.py's `_assign_scope_area`),
purely cosmetic. An earlier design routed untracked writes through it
via a `scope_for()` area/device/entity resolver, for the handful of
call sites with no caller to ask (the state-change listener, staleness
pruning). That resolver was removed once it turned out to be
unreachable in practice: every one of those call sites already requires
an entity to be claimed *somewhere* before it does anything, which the
direct claims-dict scan below always finds first - so the target-based
fallback's result was computed and then unconditionally discarded,
never once read. grouping.py's externally_set() and
override_protection.classify() own the comparison itself; this module
only records.

Persisted across restarts, on the tracking entity itself.
_StateTrackingSensor is a RestoreEntity, so its claims ride HA's own
restore state: one source of truth, the same object override protection
reads, rather than a separate Store kept in step - which is why #99
removed the original Store. A restart therefore no longer hands every
overridden light back; a bulb someone set purple stays theirs.

Restored claims are judged by VALUE, not context. A restart gives every
entity a fresh context.id, so no restored claim can match on context;
classify() falls back to comparing live values against each claim's
recorded target. Unchanged across the restart reads `controlled`,
different reads `overridden`. That value fallback (#78) is what makes
this safe - the first persisted version predated it, and excluded every
tracked light in the house after every restart (#69).

HA saves restore state every 15 minutes and at shutdown, so a crash can
lose up to 15 minutes of claims. Those lights fail open - untracked, and
so manageable - which is what every restart used to do.

Two claims per entity, not one
------------------------------
- `observed` - a state we have seen and know is safe to write over.
- `latest`   - the most recent write we sent, not yet re-observed.

`observed` is deliberately not "a write of ours". It is populated two
ways, only one of which we authored: a write an earlier call saw the
bulb adopt, and the pre-write baseline for a first-ever write. What they
share is confidence, not authorship - in both cases nothing unexplained
has happened to the light, so writing over it is safe.

apply_lighting records the context it *issued*; nothing waits to confirm
the bulb adopted it. With a single record, one dropped write locks a
light out permanently - the next tick compares the light's real,
unchanged context against a value the device never adopted, and nothing
that happens afterward can ever make those equal. (Seen live: a light
dropped a colour command at a phase boundary and sat excluded for over
an hour, correctly lit the whole time.)

Two slots fix that without needing a growing history. If the live
context matches `latest`, that attempt is now known-good and is promoted
(`observed <- latest`) before the new attempt overwrites `latest`. If it
still matches the old `observed`, `latest` never landed and `observed`
is left exactly as it was. Either way the light is still recognised as
ours and retried next tick. `observed` is only ever evicted by a fresh
observation, so it survives any number of consecutive dropped writes.

An entity's very first write has no `observed` to fall back on, so the
context.id live *before* that write is recorded as `observed` instead.
That isn't claiming ownership of it - it's the same "nothing
unexplained has happened" signal every later dropped write relies on,
since a dropped first write leaves the context at exactly that value.
See async_record.

Why a context mismatch still isn't proof
-----------------------------------------
HA's Entity._context expires 5 seconds after the service call that set
it (homeassistant/core.py), so a device whose Zigbee/MQTT round-trip
confirmation takes longer reports back under an unrelated context while
echoing exactly the value asked for. Each claim therefore also records
its `target` (brightness plus colour temperature or RGB, or None for a
claim that isn't a real write), and classify() falls back to comparing
the entity's current values against either claim's target before
concluding "external".

Device recovery and restarts
-----------------------------
async_start_listening() clears an entity's record when it is observed
dropping from a real on/off state to unavailable/unknown, so a genuine
reconnect - a state report we can't intercept, carrying a fresh context
- finds no claim to conflict with, and the light is simply managed again.

There is deliberately NO "recovery" re-baseline. There used to be: any
transition into a real state from unavailable/unknown or no prior state
replaced `observed` with the live context. But a genuine dropout has
already had its record cleared by then, so that branch only ever fired
on a restart or an integration reload - and with claims restored, it
would re-baseline every light as ours, overrides included, moments after
the restore. The value fallback in classify() does that job properly
now. It could not have been kept by keying on HA's `restored: True`
placeholder attribute: MQTT lights reach `on` from their own untagged
`unknown` state (unavailable -> unknown -> on, confirmed live).

Both remaining rules must START from a real on/off state, not merely end
somewhere. Nearly every entity passes through unavailable/unknown on
every restart. Clearing on the destination alone wiped protection for
practically every light in the house (#57); releasing a scope on any
transition to `off` would let the first light to reconnect as `off`
release restored overrides on siblings still reconnecting.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Optional, Protocol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SUBENTRY_TYPE_STATE
from .override_protection import _context_matches, _ContextClaim, _WriteRecord

# How long a tracked record is kept after it was last written or
# observed, before async_prune_stale() discards it outright - see that
# method's own docstring for why this exists at all (an entity deleted
# from HA entirely, not just restarting, has no event this integration
# can observe to know it should stop tracking it). Deliberately short:
# pruning a record is never actually risky, regardless of how soon it
# happens - classify() treats "no record at all" identically to
# "unclaimed" (see its own docstring), never as blocked, so a pruned
# light simply looks brand-new again and re-establishes a real record
# on its next write. There's no lockout to guard against by being
# conservative here, so there's no reason to hold onto a record for a
# still-real, still-relevant light any longer than "hasn't needed a
# write in a day" already implies it's not needed.
STALE_RECORD_MAX_AGE_DAYS = 1

# How often async_prune_stale() actually gets called while running (in
# addition to once at startup, in __init__.py) - with a one-day cutoff,
# only pruning at startup would mean a record could sit stale for as
# long as HA happens to stay up between restarts before ever being
# cleaned, which defeats "a day" as a real promise. Frequent enough to
# keep that promise, infrequent enough that it costs nothing meaningful
# (a plain dict scan over however many entities are tracked, typically
# a few dozen).
PRUNE_CHECK_INTERVAL = timedelta(hours=1)

# Fired (with no payload - listeners re-read through the registry)
# whenever any scope's claims change, so the per-scope count sensors
# refresh immediately instead of polling.
SIGNAL_WRITE_TRACKING_UPDATED = "flare_claims_updated"


class ClaimStore(Protocol):
    """What ClaimRegistry needs from a state device's tracking entity.

    Declared structurally rather than importing sensor.py, which would
    be circular - sensor.py imports this module."""

    claims: dict[str, _WriteRecord]

    def async_claims_changed(self) -> None:
        """Publish the mutated claims as the entity's own state."""


class ClaimRegistry:
    """Routes each light to the state device that tracks it, and reads
    and writes that device's claims.

    Holds no claims of its own. The dict lives on the state device's
    tracking entity, which publishes it as an attribute - so what
    governs behaviour and what you can see in Developer Tools are the
    same object, not a copy kept in step by convention."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._stores: dict[str, ClaimStore] = {}

    @callback
    def register(self, subentry_id: str, store: ClaimStore) -> None:
        self._stores[subentry_id] = store

    @callback
    def unregister(self, subentry_id: str) -> None:
        self._stores.pop(subentry_id, None)

    def resolve_scope_device(self, device_id: str | None) -> str | None:
        """Turns a service call's tracking_device_id into the subentry_id
        every read/write method below actually wants.

        None in, None out: omitting tracking_device_id means "don't track
        this write", not "go find out where it belongs" - the caller
        said nothing, so nothing is recorded, same as every other
        untracked-light case. A device_id that IS given but isn't one of
        this tracking entry's own state devices is a caller mistake, not
        an absent scope, so it raises rather than silently degrading to
        untracked - a typo'd or stale device_id should be loud."""
        if device_id is None:
            return None
        device = dr.async_get(self._hass).async_get(device_id)
        subentry_id = next(
            (sid for (domain, sid) in (device.identifiers if device else ()) if domain == DOMAIN),
            None,
        )
        subentry = self._entry.subentries.get(subentry_id) if subentry_id else None
        if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_STATE:
            raise ServiceValidationError(f"{device_id} is not a FLARE tracking scope")
        return subentry_id

    def title_for_scope(self, subentry_id: str | None) -> str | None:
        """The scope's display name, for echoing back in a service
        response - claims_check's own "scope" field, for example."""
        if subentry_id is None:
            return None
        subentry = self._entry.subentries.get(subentry_id)
        return subentry.title if subentry is not None else None

    def _store_for(self, entity_id: str) -> ClaimStore | None:
        """The live tracking entity holding this light's claims, or None
        if it isn't tracked anywhere.

        A claim lives wherever it was most recently recorded (async_record's
        caller-supplied subentry_id) - never resolved from the entity's own
        area/device, so re-pointing a state device's target can't strand an
        existing claim in a scope nothing reads any more, and an untracked
        entity simply has no home to find here."""
        for store in self._stores.values():
            if entity_id in store.claims:
                return store
        return None

    def _record(self, subentry_id: str | None, entity_id: str) -> _WriteRecord | None:
        """The one place decision-3's "no scope, no tracking" is
        implemented for reads: a None scope means nothing to look up,
        full stop, not a search for where the light might live."""
        if subentry_id is None:
            return None
        store = self._stores.get(subentry_id)
        return store.claims.get(entity_id) if store else None

    def all_records(self) -> dict[str, _WriteRecord]:
        """Every tracked light across every scope, flattened. A light
        can only appear once - _store_for keeps it in one scope."""
        merged: dict[str, _WriteRecord] = {}
        for store in self._stores.values():
            merged.update(store.claims)
        return merged

    def records_for_scope(self, subentry_id: str) -> dict[str, _WriteRecord]:
        store = self._stores.get(subentry_id)
        return dict(store.claims) if store else {}

    @callback
    def _notify(self, stores: Iterable[ClaimStore]) -> None:
        for store in stores:
            store.async_claims_changed()
        async_dispatcher_send(self._hass, SIGNAL_WRITE_TRACKING_UPDATED)

    def observed_context_id(self, subentry_id: str | None, entity_id: str) -> str | None:
        record = self._record(subentry_id, entity_id)
        claim = record.get("observed") if record else None
        return claim["context_id"] if claim else None

    def observed_target(self, subentry_id: str | None, entity_id: str) -> dict | None:
        record = self._record(subentry_id, entity_id)
        claim = record.get("observed") if record else None
        return claim.get("target") if claim else None

    def observed_secondary_context_id(self, subentry_id: str | None, entity_id: str) -> str | None:
        record = self._record(subentry_id, entity_id)
        claim = record.get("observed") if record else None
        return claim.get("secondary_context_id") if claim else None

    def latest_context_id(self, subentry_id: str | None, entity_id: str) -> str | None:
        record = self._record(subentry_id, entity_id)
        claim = record.get("latest") if record else None
        return claim["context_id"] if claim else None

    def latest_target(self, subentry_id: str | None, entity_id: str) -> dict | None:
        record = self._record(subentry_id, entity_id)
        claim = record.get("latest") if record else None
        return claim.get("target") if claim else None

    def latest_secondary_context_id(self, subentry_id: str | None, entity_id: str) -> str | None:
        record = self._record(subentry_id, entity_id)
        claim = record.get("latest") if record else None
        return claim.get("secondary_context_id") if claim else None

    async def async_clear(self, subentry_id: str | None, entity_ids: list[str]) -> None:
        """Manually discards entities' tracked records within one scope -
        deliberately invoked, unlike every other path that removes a
        record (async_start_listening's drop-detection, which only ever
        fires on an *observed* unavailable transition). Backs the
        claims_clear service - the escape hatch for a light that's landed
        in "overridden" without ever actually going unavailable, and so
        has no other way back: build_groups() (grouping.py) never calls
        async_record for anything externally_set() already excludes, so
        an overridden light's own `latest` target only gets staler
        over time and can never refresh itself on a ramping curve -
        confirmed live, several kitchen lights during a Day-phase Kelvin
        ramp, correctly lit the whole time but permanently excluded once
        the live colour temperature drifted a single Kelvin past the
        rescue tolerance of a `latest` claim that was itself frozen the
        moment exclusion began. A no-op with no scope, or for an entity
        with no record in that scope."""
        # subentry_id=None finds no store here just as naturally as a
        # real id with nothing registered - dict.get(None) is simply
        # never a key, same reasoning as async_record's own lookup.
        store = self._stores.get(subentry_id)
        if store is None:
            return
        # Not any(store.claims.pop(...) ... for ...): any() short-circuits
        # on the first True, and pop() is what actually clears each claim
        # - a generator here would stop popping after the first entity
        # that had one, leaving every entity after it in the list
        # untouched. Confirmed live as the cause of "clear" needing one
        # press per light instead of clearing the whole scope at once.
        popped = [store.claims.pop(entity_id, None) for entity_id in entity_ids]
        if any(value is not None for value in popped):
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
        """Called once per apply_lighting invocation, with every entity it
        actually issued a light.turn_on/turn_off for - not ones it merely
        considered. See the module docstring for the two-claim model this
        maintains; this documents the arguments.

        subentry_id is the caller's scope, resolved once for the whole
        call - not re-derived per entity. A None scope means "write the
        light, track nothing", the decision-3 behaviour: this returns
        immediately and no claim is recorded for any of entity_ids.

        If a light was previously tracked under a *different* scope (its
        automation's target changed, or a different caller now names it
        under a different scope), the old claim is left where it is
        rather than migrated - see the module's own note on why that's
        deliberate. It goes stale and is pruned in the ordinary course,
        or a Clear press removes it sooner.

        live_context_before_write: each entity's context.id as read
        *before* any of this call's writes were dispatched. It cannot be
        read fresh in here - by the time this runs the writes have been
        awaited, so a light's live context may already reflect the very
        write about to be recorded as `latest`, making every write look
        like it promoted itself instantly.

        This is the one and only place promotion happens: if the previous
        `latest` claim matches what was live just before this write went
        out, that attempt is proven landed and becomes `observed`.
        Otherwise `observed` is left untouched and only `latest` is
        replaced. The exception is an entity's first-ever write, which has
        no `observed` to fall back on - the pre-write context is recorded
        as `observed`, so a dropped first write still
        has a retry signal, and that synthetic baseline never blocks
        anyone else's claim.

        targets: per entity, what this write asked for. An entity missing
        from it (an off-command has no colour target) gets None.

        secondary_context_ids / context_id_overrides: two-step entities
        only. Those writes go out as two light.turn_on calls under two
        distinct contexts, neither of which is `context_id` above (the
        triggering call's own, never passed to either). The overrides
        supply the colour step as the claim's primary context; the
        secondaries supply the brightness step. Both stay empty for
        everything else, which keeps using `context_id` alone."""
        if not entity_ids:
            return
        # subentry_id=None (decision 3, "don't track this") finds no
        # store here just as naturally as a real id whose tracking
        # entity isn't up yet (services are registered before platforms
        # are forwarded - see __init__.py) - one guard covers both,
        # deliberately not a separate `if subentry_id is None` check.
        store = self._stores.get(subentry_id)
        if store is None:
            # Dropped, not queued: a lighting override that goes
            # unrecorded for one tick costs nothing, and the next tick
            # records it properly.
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
        self._notify([store])

    async def async_prune_stale(self) -> None:
        """Discards any tracked record not written or observed in over
        STALE_RECORD_MAX_AGE_DAYS days - the cleanup an entity genuinely
        *deleted* from HA never otherwise gets. Every other cleanup path
        here needs `hass.states.get()` to return *something* to act on;
        a removed entity returns None forever and is silently skipped by
        all of them, leaving its record stranded.

        Called once at startup and every PRUNE_CHECK_INTERVAL after - a
        startup-only pass would let records sit stale for however long HA
        stays up.

        Deliberately aggressive on timing, unlike most decisions here:
        pruning too soon has no failure mode, since classify() treats "no
        record" as `unclaimed`, never as blocked. A record with no
        parseable `last_seen` is left alone - when age can't be judged,
        the same "don't delete on ambiguity" preference used elsewhere."""
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
        """Discards a scope's claims once none of the lights it tracks
        are on.

        Turning a light off is an override like any other (see
        override_protection.classify), so a light switched off by hand
        stays off rather than being relit on the next tick. Something
        has to end that, and the whole room going dark is the signal:
        nobody is using the room, so nobody's choice is being
        overridden by handing it back.

        Anything not reporting `on` counts as dark, including
        unavailable and unknown. Requiring every tracked light to
        report `off` would let one permanently unavailable entity - an
        orphaned Zigbee group, say - veto the release forever, which is
        the same trap the blueprint's `recovered` trigger avoids by
        asking whether anything is reachable rather than whether
        nothing is unavailable."""
        if not store.claims:
            return
        for entity_id in store.claims:
            state = self._hass.states.get(entity_id)
            if state is not None and state.state == "on":
                return
        store.claims.clear()

    def async_start_listening(self, hass: HomeAssistant) -> CALLBACK_TYPE:
        """Watches every tracked entity through one hass-wide
        "state_changed" listener - cheaper than keeping per-entity
        subscriptions in sync with the tracked set as apply_lighting adds
        entities over time. The module docstring's "Device recovery and
        restarts" explains the shape of each rule.

        - **Drop** (a real on/off state -> unavailable/unknown): clears
          the record, so the eventual reconnect finds nothing to
          conflict with.
        - **Off** (a real on/off state -> off): re-checks whether the
          scope has gone dark, and releases it if so.

        Both require the STARTING state to be a real on/off state. Almost
        every entity passes through unavailable/unknown on every restart,
        and reacting to the destination alone either wiped protection
        house-wide or, with claims restored, would release a scope while
        half its lights were still reconnecting."""

        @callback
        def _on_state_changed(event: Event[EventStateChangedData]) -> None:
            entity_id = event.data["entity_id"]
            store = self._store_for(entity_id)
            if store is None or entity_id not in store.claims:
                return
            old_state = event.data["old_state"]
            new_state = event.data["new_state"]
            old_available = old_state is not None and old_state.state not in ("unavailable", "unknown")
            # Drop requires new_state to explicitly report "unavailable"/
            # "unknown" - not new_state being absent entirely (an entity
            # removed from the state machine, as every entity is across a
            # restart before it re-registers). Treating "gone" as
            # "unavailable" would clear every record at every restart.
            new_explicitly_unavailable = new_state is not None and new_state.state in ("unavailable", "unknown")
            dropped = old_available and new_explicitly_unavailable
            # A real on/off -> off only. `unknown -> off` is a light
            # reconnecting after a restart, not somebody switching it off,
            # and releasing on it would let the first light back release
            # restored overrides on siblings still reconnecting.
            went_off = old_available and new_state is not None and new_state.state == "off"

            if dropped:
                store.claims.pop(entity_id, None)
            elif not went_off:
                return

            # Either way the scope may now be dark: a light went off, or
            # a light dropped and its claim was just popped.
            self._release_if_dark(store)

            self._notify([store])

        return hass.bus.async_listen("state_changed", _on_state_changed)
