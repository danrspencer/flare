"""Rooms and the claim events: claims are FLARE's, one per light, and a
room - whatever a caller names, usually its automation - releases the
lights it wrote together. Also the counts, Clear and the events."""

from datetime import timedelta

import pytest

from freezegun import freeze_time

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.flare.button import async_setup_entry as button_setup
from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_SETTINGS,
    SUBENTRY_TYPE_SENSOR,
)
from custom_components.flare.schedule.coordinator import ScheduleCoordinator, schedule_instances
from custom_components.flare.sensor import CONTROLLED_GATHER_SECONDS, ClaimEvents
from custom_components.flare.sensor import async_setup_entry as sensor_setup
from custom_components.flare.tracking.claims import SIGNAL_CLAIMS_UPDATED, ClaimRegistry
from custom_components.flare.tracking.override_protection import MISMATCH_GRACE
from tests.support.claims import after_the_grace, claim_field

ASKED = {"brightness": 200, "color_temp_kelvin": 3000}
KITCHEN = "automation.kitchen"
HALL = "automation.hall"


_TRACKERS: list = []


@pytest.fixture(autouse=True)
async def _stop_trackers(hass: HomeAssistant):
    """Cancels the claim events' pending timers."""
    yield
    while _TRACKERS:
        _TRACKERS.pop()._cancel_timers()


async def _setup(hass: HomeAssistant):
    """The Settings entry with its real entities attached."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS}, version=3, minor_version=2)
    entry.add_to_hass(hass)
    registry = ClaimRegistry(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = registry

    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    await button_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    # The tests refresh the statuses themselves.
    tracker = registry._listener
    tracker.async_claims_changed = lambda: None
    added.append(tracker)
    _TRACKERS.append(tracker)
    return entry, registry, added


def _tracker(added: list) -> ClaimEvents:
    return next(e for e in added if isinstance(e, ClaimEvents))


def _entity(added: list, entity_id: str):
    return next(e for e in added if e.entity_id == entity_id)


def _light(hass: HomeAssistant, entity_id: str, *, state="on", **attrs):
    hass.states.async_set(entity_id, state, {"brightness": 200, "color_temp_kelvin": 3000, **attrs}, context=Context())


async def _record(registry: ClaimRegistry, room: str | None, entity_id: str, context_id: str, target=None, room_lights=None):
    await registry.async_record(
        room,
        [entity_id],
        {entity_id: f"before-{entity_id}"},
        context_id,
        targets={entity_id: target} if target else None,
        room_entities=room_lights,
    )


async def test_a_write_naming_no_room_is_not_tracked(hass: HomeAssistant):
    """Only a caller naming a room makes a light tracked."""
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.elsewhere")

    await _record(registry, None, "light.elsewhere", "ctx-1", ASKED)
    assert registry.all_records() == {}
    assert claim_field(registry, "light.elsewhere", "latest", "context_id") is None


async def test_a_room_named_by_an_automation_survives_its_rename(hass: HomeAssistant):
    """Keyed by the entity's registry id, which a rename keeps."""
    _entry, registry, _ = await _setup(hass)
    entity = er.async_get(hass).async_get_or_create("automation", "automation", "kitchen", suggested_object_id="kitchen")
    _light(hass, "light.a")
    _light(hass, "light.b")
    await _record(registry, entity.entity_id, "light.a", "ctx-1", ASKED)

    er.async_get(hass).async_update_entity(entity.entity_id, new_entity_id="automation.kitchen_lighting")
    await _record(registry, "automation.kitchen_lighting", "light.b", "ctx-2", ASKED)

    assert registry.rooms_of("light.a") == registry.rooms_of("light.b") == [entity.id]
    assert registry.room_entity_id(entity.id) == "automation.kitchen_lighting"


async def test_counters_split_the_lights_by_status(hass: HomeAssistant):
    _entry, registry, added = await _setup(hass)
    controlled = _entity(added, "sensor.flare_controlled_lights")
    overridden = _entity(added, "sensor.flare_overridden_lights")

    ours = Context()
    _light(hass, "light.mine")
    _light(hass, "light.taken")
    await _record(registry, KITCHEN, "light.mine", ours.id, ASKED)
    await _record(registry, KITCHEN, "light.taken", "ctx-ours", ASKED)
    hass.states.async_set("light.mine", "on", ASKED, context=ours)
    hass.states.async_set("light.taken", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    registry.note_mismatches()

    assert (controlled.native_value, overridden.native_value) == (1, 0), "mismatched: in neither yet"
    with after_the_grace():
        assert controlled.native_value == 1
        assert overridden.native_value == 1
        assert overridden.extra_state_attributes["lights"] == ["light.taken"]
        assert controlled.extra_state_attributes["total_tracked"] == 2


async def test_two_rooms_writing_one_light_share_its_claim(hass: HomeAssistant):
    """Claims are FLARE's: the second automation's write isn't an override of
    the first's, and nothing warns about it."""
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.shared")

    await _record(registry, KITCHEN, "light.shared", "ctx-kitchen", ASKED)
    await _record(registry, HALL, "light.shared", "ctx-hall", {"brightness": 120, "color_temp_kelvin": 2700})

    assert list(registry.all_records()) == ["light.shared"]
    assert claim_field(registry, "light.shared", "latest", "context_id") == "ctx-hall"
    assert registry.rooms_of("light.shared") == sorted([KITCHEN, HALL])
    assert persistent_notification._async_get_or_create_notifications(hass) == {}


async def test_an_unavailable_light_holding_a_claim_does_not_hold_a_room_open(hass: HomeAssistant):
    """Anything not `on` is dark, so one dead entity can't hold a room open.
    The claim predates the listener, as after a restart."""
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.a")
    _light(hass, "light.dead")
    for e in ("light.a", "light.dead"):
        await _record(registry, KITCHEN, e, "ctx-ours", ASKED)

    hass.states.async_set("light.dead", "unavailable", {})
    await hass.async_block_till_done()
    assert set(registry.all_records()) == {"light.a", "light.dead"}, "precondition: the claim survives"

    unsub = registry.async_start_listening(hass)
    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()

    assert registry.all_records() == {}
    unsub()


async def test_a_room_light_flare_never_claimed_does_not_hold_it_open(hass: HomeAssistant):
    """A lamp in the room that FLARE leaves alone, on all evening, mustn't
    stop the room's claims ever being released."""
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.a")
    _light(hass, "light.tv_backlight")
    await _record(registry, KITCHEN, "light.a", "ctx-ours", ASKED, room_lights=["light.a", "light.tv_backlight"])
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()

    assert registry.all_records() == {}
    unsub()


async def test_a_light_switched_off_while_another_of_the_rooms_lights_is_on_keeps_its_claim(hass: HomeAssistant):
    """The room's lights are every light it named, not only those this write
    sent to, so a light written earlier still holds the room open."""
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.a")
    _light(hass, "light.b")
    await _record(registry, KITCHEN, "light.b", "ctx-b", ASKED)
    await _record(registry, KITCHEN, "light.a", "ctx-a", ASKED, room_lights=["light.a"])
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.a", "light.b"}
    unsub()


async def test_rooms_release_independently(hass: HomeAssistant):
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.k")
    _light(hass, "light.h")
    await _record(registry, KITCHEN, "light.k", "ctx-ours", ASKED)
    await _record(registry, HALL, "light.h", "ctx-ours", ASKED)
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.k", "off", {})
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.h"}
    unsub()


async def test_a_light_in_two_rooms_is_released_when_either_goes_dark(hass: HomeAssistant):
    """Its claim is FLARE's, so the first room to go dark lets it go."""
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.shared")
    _light(hass, "light.h")
    await _record(registry, KITCHEN, "light.shared", "ctx-k", ASKED)
    await _record(registry, HALL, "light.shared", "ctx-h", ASKED, room_lights=["light.shared", "light.h"])
    await _record(registry, HALL, "light.h", "ctx-h", ASKED)
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.shared", "off", {})
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.h"}
    unsub()


async def test_the_clear_button_clears_every_claim(hass: HomeAssistant):
    _entry, registry, added = await _setup(hass)
    _light(hass, "light.k")
    _light(hass, "light.h")
    await _record(registry, KITCHEN, "light.k", "ctx-k", ASKED)
    await _record(registry, HALL, "light.h", "ctx-h", ASKED)

    button = _entity(added, "button.flare_clear")
    assert button.extra_state_attributes["tracked"] == 2
    await button.async_press()

    assert registry.all_records() == {}


async def test_the_override_event_names_the_light_and_its_rooms(hass: HomeAssistant):
    """Filed under the overridden count, which is how the Activity card knows
    its kind."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)

    _light(hass, "light.a")
    await _record(registry, KITCHEN, "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()  # seeds without announcing
    assert events == []

    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()
    assert events == [], "mismatched, not yet an override"
    with after_the_grace():
        tracker._refresh_statuses()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["entity_id"] == "sensor.flare_overridden_lights"
    assert events[0].data["light"] == "light.a"
    assert events[0].data["rooms"] == [KITCHEN]
    assert events[0].data["live"]["brightness"] == 12
    assert events[0].data["latest"]["target"] == ASKED


async def _stops_matching(hass: HomeAssistant):
    """One light that has just stopped matching its claims, as when a bulb
    back online reports a stale level before FLARE's resend lands."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)
    _light(hass, "light.a", state="unavailable")
    await _record(registry, KITCHEN, "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()
    hass.states.async_set("light.a", "on", {"brightness": 10, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()
    await hass.async_block_till_done()
    return tracker, events, _entity(added, "sensor.flare_overridden_lights")


async def test_a_light_that_stops_matching_is_not_shown_overridden_at_first(hass: HomeAssistant):
    tracker, events, overridden = await _stops_matching(hass)

    assert events == []
    assert overridden.native_value == 0


async def test_a_light_still_mismatched_after_the_grace_is_announced_and_counted(hass: HomeAssistant):
    _tracker, events, overridden = await _stops_matching(hass)
    refreshed: list = []
    async_dispatcher_connect(hass, SIGNAL_CLAIMS_UPDATED, lambda: refreshed.append(True))

    later = dt_util.utcnow() + MISMATCH_GRACE + timedelta(seconds=2)
    with freeze_time(later, real_asyncio=True):
        async_fire_time_changed(hass, later)
        await hass.async_block_till_done()
        assert overridden.native_value == 1
    assert refreshed, "the count sensors are told to refresh"

    assert [e.data["light"] for e in events] == ["light.a"]


async def test_a_light_that_comes_back_to_what_flare_asked_for_is_never_announced(hass: HomeAssistant):
    tracker, events, overridden = await _stops_matching(hass)
    hass.states.async_set("light.a", "on", ASKED, context=Context())
    tracker._refresh_statuses()

    later = dt_util.utcnow() + MISMATCH_GRACE + timedelta(seconds=2)
    with freeze_time(later, real_asyncio=True):
        async_fire_time_changed(hass, later)
        await hass.async_block_till_done()
        assert overridden.native_value == 0

    assert events == []


async def test_a_light_set_again_after_an_override_is_not_announced(hass: HomeAssistant):
    """Churn, not news: neither taken nor anything else."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    _light(hass, "light.a")
    await _record(registry, KITCHEN, "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()
    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()
    with after_the_grace():
        tracker._refresh_statuses()

    hass.states.async_set("light.a", "on", ASKED, context=Context())
    tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()

    assert events == []


async def test_a_room_going_dark_says_it_cleared_its_lights(hass: HomeAssistant):
    _entry, registry, _ = await _setup(hass)
    events: list = []
    hass.bus.async_listen("flare_lights_released", events.append)
    for light in ("light.a", "light.b"):
        _light(hass, light)
        await _record(registry, KITCHEN, light, f"ctx-{light}", ASKED)
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()
    assert events == [], "one light still on"
    hass.states.async_set("light.b", "off", {})
    await hass.async_block_till_done()
    unsub()

    assert [(e.data["lights"], e.data["room"], e.data["entity_id"]) for e in events] == [
        (["light.a", "light.b"], KITCHEN, "button.flare_clear")
    ]


async def test_clear_says_it_cleared_once_per_room_but_claims_clear_is_silent(hass: HomeAssistant):
    """The service is the blueprint's bookkeeping, run as lights are handed off."""
    _entry, registry, added = await _setup(hass)
    events: list = []
    hass.bus.async_listen("flare_lights_released", events.append)
    for light, room in (("light.a", KITCHEN), ("light.b", KITCHEN), ("light.h", HALL)):
        _light(hass, light)
        await _record(registry, room, light, f"ctx-{light}", ASKED)

    await registry.async_clear(["light.a"])
    await hass.async_block_till_done()
    assert events == []

    await _entity(added, "button.flare_clear").async_press()
    await hass.async_block_till_done()

    assert sorted((e.data["room"], e.data["lights"]) for e in events) == [(HALL, ["light.h"]), (KITCHEN, ["light.b"])]


async def test_lights_a_room_takes_are_announced_together(hass: HomeAssistant):
    """flare_lights_controlled: one entry for a room coming on, not one per
    bulb as each reports back."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    tracker._refresh_statuses()  # seeds without announcing

    for light in ("light.a", "light.b"):
        _light(hass, light)
        await _record(registry, KITCHEN, light, f"ctx-{light}", ASKED)
        tracker._refresh_statuses()
    assert events == [], "gathered first"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()
    tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2 * CONTROLLED_GATHER_SECONDS + 2))
    await hass.async_block_till_done()

    assert [e.data for e in events] == [
        {
            "lights": ["light.a", "light.b"],
            "controlled": 2,
            "room": KITCHEN,
            "entity_id": "sensor.flare_controlled_lights",
        }
    ], "once, and not again for lights it already had"


async def test_two_rooms_coming_on_together_are_announced_separately(hass: HomeAssistant):
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    tracker._refresh_statuses()

    for light, room in (("light.k", KITCHEN), ("light.h", HALL)):
        _light(hass, light)
        await _record(registry, room, light, f"ctx-{light}", ASKED)
        tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()

    assert sorted((e.data["room"], e.data["lights"]) for e in events) == [(HALL, ["light.h"]), (KITCHEN, ["light.k"])]


async def test_lights_taken_only_to_switch_them_off_are_not_announced(hass: HomeAssistant):
    """A turn-off claims lights too; the room is dark, so nothing was taken."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    tracker._refresh_statuses()

    _light(hass, "light.a", state="off")
    await _record(registry, HALL, "light.a", "ctx-ours", {"state": "off"})
    tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()

    assert events == []


async def test_a_light_coming_back_online_is_not_announced_as_taken(hass: HomeAssistant):
    """As every light does after a restart: it was already the room's."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    _light(hass, "light.a")
    await _record(registry, KITCHEN, "light.a", "ctx-ours", ASKED)
    hass.states.async_set("light.a", "unavailable", {}, context=Context())
    tracker._refresh_statuses()  # seeds: unavailable

    hass.states.async_set("light.a", "on", ASKED, context=Context())
    tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()

    assert events == []


async def test_counters_refresh_when_a_lights_live_state_changes(hass: HomeAssistant):
    """The counts depend on live state, which changes with no claim changing.
    Unavailable rather than off: off with someone else's claim is still
    overridden."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    overridden = _entity(added, "sensor.flare_overridden_lights")

    _light(hass, "light.a")
    await _record(registry, KITCHEN, "light.a", "ctx-ours", ASKED)
    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()
    with after_the_grace():
        assert overridden.native_value == 1

    refreshed: list = []
    async_dispatcher_connect(hass, SIGNAL_CLAIMS_UPDATED, lambda: refreshed.append(True))

    hass.states.async_set("light.a", "unavailable", {})
    tracker._poll(None)
    await hass.async_block_till_done()

    assert refreshed, "the poll must tell the counters to recompute"
    assert overridden.native_value == 0


async def test_each_entry_type_owns_only_its_own_sensors(hass: HomeAssistant):
    """Both entry types use the sensor platform."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_SENSOR, title="Ground Floor", unique_id="ground_floor", data={}
            )
        ],
    )
    entry.add_to_hass(hass)
    for instance in schedule_instances(entry):
        coordinator = ScheduleCoordinator(hass, instance)
        # Plain refresh: first_refresh needs a real entry setup.
        await coordinator.async_refresh()
        hass.data.setdefault(DOMAIN, {})[instance.subentry_id] = coordinator

    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))

    assert [e.entity_id for e in added] == ["sensor.ground_floor_flare"]
    assert not any(hasattr(e, "claims") for e in added)


async def test_a_room_switched_off_by_something_else_goes_dark_without_overrides(hass: HomeAssistant):
    """Each light is only mismatched as it goes off, and the room lets them
    all go once it's dark, before any could count as overridden."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)
    for light in ("light.a", "light.b"):
        _light(hass, light, **ASKED)
        await _record(registry, KITCHEN, light, f"ctx-{light}", ASKED)
    tracker._refresh_statuses()
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.a", "off", {}, context=Context())
    await hass.async_block_till_done()
    tracker._refresh_statuses()
    hass.states.async_set("light.b", "off", {}, context=Context())
    await hass.async_block_till_done()
    with after_the_grace():
        tracker._refresh_statuses()
    unsub()

    assert events == []
    assert registry.all_records() == {}


async def test_flares_own_write_landing_is_never_an_override(hass: HomeAssistant):
    """Recorded before it's sent, so the light briefly shows the last value;
    the mismatch clears when the new one arrives."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)
    _light(hass, "light.a", **ASKED)
    await _record(registry, KITCHEN, "light.a", "ctx-first", ASKED)
    tracker._refresh_statuses()
    unsub = registry.async_start_listening(hass)

    later = {"brightness": 120, "color_temp_kelvin": 2700}
    await _record(registry, KITCHEN, "light.a", "ctx-second", later)
    assert claim_field(registry, "light.a", "latest", "context_id") == "ctx-second"
    assert registry.record("light.a").get("mismatch_since"), "noted while the write is in flight"
    tracker._refresh_statuses()
    hass.states.async_set("light.a", "on", later, context=Context(id="ctx-second"))
    await hass.async_block_till_done()
    with after_the_grace():
        tracker._refresh_statuses()
    unsub()

    assert "mismatch_since" not in registry.record("light.a")
    assert events == []


async def test_claims_override_is_an_override_at_once(hass: HomeAssistant):
    """Someone said so, as a flare does, so there's nothing to wait for."""
    _entry, registry, added = await _setup(hass)
    tracker = _tracker(added)
    overridden = _entity(added, "sensor.flare_overridden_lights")
    _light(hass, "light.a", **ASKED)

    await registry.async_override(KITCHEN, ["light.a"])
    tracker._refresh_statuses()

    assert overridden.native_value == 1
    assert registry.rooms_of("light.a") == [KITCHEN], "released with its room"


async def test_a_claimed_light_is_not_adopted(hass: HomeAssistant):
    """Whichever room claimed it."""
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.a", **ASKED)
    await _record(registry, HALL, "light.a", "ctx-hall", ASKED)

    registry.adopt(KITCHEN, ["light.a"])

    assert claim_field(registry, "light.a", "latest", "context_id") == "ctx-hall"


async def test_an_adopted_light_is_released_with_its_room(hass: HomeAssistant):
    _entry, registry, _ = await _setup(hass)
    _light(hass, "light.a", **ASKED)
    unsub = registry.async_start_listening(hass)

    registry.adopt(KITCHEN, ["light.a"])
    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()

    assert registry.all_records() == {}
    unsub()
