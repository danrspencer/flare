"""Zones: their entities hold the claims, the
counts, the Clear button, the override event and area placement. A light's
zone is whichever one a caller names, never resolved from its area."""

from datetime import timedelta

from freezegun import freeze_time

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.flare.button import async_setup_entry as button_setup
from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_ZONES,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_ZONE,
)
from custom_components.flare.schedule.coordinator import ScheduleCoordinator, schedule_instances
from custom_components.flare.sensor import CONTROLLED_GATHER_SECONDS
from custom_components.flare.sensor import async_setup_entry as sensor_setup
from custom_components.flare.zone.instance import zone_instances
from custom_components.flare.zone.claims import RECONNECTS, SIGNAL_CLAIMS_UPDATED, ClaimRegistry
from custom_components.flare.zone.override_protection import RECONNECT_SETTLE
from tests.support.claims import claim_field

ASKED = {"brightness": 200, "color_temp_kelvin": 3000}


def _zone(title: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type=SUBENTRY_TYPE_ZONE, title=title, unique_id=title.lower().replace(" ", "_"), data={}
    )


async def _setup(hass: HomeAssistant, *zones: ConfigSubentryData):
    """An entry with these zones and their real entities attached."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES}, subentries_data=list(zones)
    )
    entry.add_to_hass(hass)
    registry = ClaimRegistry(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = registry

    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    await button_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    trackers = [e for e in added if hasattr(e, "claims")]
    for instance, tracker in zip(zone_instances(entry), trackers):
        tracker.async_claims_changed = lambda: None
        registry.register(instance.subentry_id, tracker)
    return entry, registry, added


def _light(hass: HomeAssistant, entity_id: str, *, area_id=None, device_id=None, state="on", **attrs):
    registry = er.async_get(hass)
    created = registry.async_get_or_create(
        "light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1], device_id=device_id
    )
    if area_id:
        registry.async_update_entity(created.entity_id, area_id=area_id)
    hass.states.async_set(
        entity_id, state, {"brightness": 200, "color_temp_kelvin": 3000, **attrs}, context=Context()
    )
    return created.entity_id


async def _record(registry: ClaimRegistry, subentry_id: str | None, entity_id: str, context_id: str, target=None):
    await registry.async_record(
        subentry_id,
        [entity_id],
        {entity_id: f"before-{entity_id}"},
        context_id,
        targets={entity_id: target} if target else None,
    )


def _zone_id(entry, title: str) -> str:
    return next(i.subentry_id for i in zone_instances(entry) if i.title == title)


async def test_a_light_with_no_zone_named_is_not_tracked_and_stays_manageable(hass: HomeAssistant):
    """Only a caller naming the zone makes a light tracked."""
    _entry, registry, _ = await _setup(hass, _zone("Kitchen"))
    _light(hass, "light.elsewhere")

    await _record(registry, None, "light.elsewhere", "ctx-1", ASKED)
    assert registry.all_records() == {}
    assert claim_field(registry, None, "light.elsewhere", "latest", "context_id") is None


async def test_a_write_before_the_zones_entity_exists_is_dropped(hass: HomeAssistant):
    """Services exist before platforms, so this can really happen."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES},
        subentries_data=[_zone("Kitchen")],
    )
    entry.add_to_hass(hass)
    registry = ClaimRegistry(hass, entry)  # no entities registered yet
    _light(hass, "light.a", area_id=area.id)

    await _record(registry, _zone_id(entry, "Kitchen"), "light.a", "ctx-1", ASKED)

    assert registry.all_records() == {}


async def test_claims_live_on_the_claims_sensor_and_are_published_there(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, added = await _setup(hass, _zone("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    _light(hass, "light.a", area_id=area.id)

    await _record(registry, _zone_id(_entry, "Kitchen"), "light.a", "ctx-1", ASKED)

    # The registry mutated this very dict.
    assert "light.a" in tracker.claims
    assert registry.all_records()["light.a"] is tracker.claims["light.a"]
    assert tracker.native_value == 1
    assert tracker.extra_state_attributes["claims"]["light.a"]["latest"]["context_id"] == "ctx-1"
    assert "claims" in tracker._unrecorded_attributes


async def test_counters_split_one_zones_lights_by_status(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, added = await _setup(hass, _zone("Kitchen"))
    controlled = next(e for e in added if e.entity_id.endswith("_flare_controlled"))
    overridden = next(e for e in added if e.entity_id.endswith("_flare_overridden"))

    zone = _zone_id(_entry, "Kitchen")
    ours = Context()
    _light(hass, "light.mine", area_id=area.id)
    _light(hass, "light.taken", area_id=area.id)
    await _record(registry, zone, "light.mine", ours.id, ASKED)
    await _record(registry, zone, "light.taken", "ctx-ours", ASKED)
    hass.states.async_set("light.mine", "on", ASKED, context=ours)
    hass.states.async_set("light.taken", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())

    assert controlled.native_value == 1
    assert overridden.native_value == 1
    assert overridden.extra_state_attributes["lights"] == ["light.taken"]
    assert controlled.extra_state_attributes["total_tracked"] == 2


async def test_two_callers_writing_one_light_share_the_zones_claims(hass: HomeAssistant):
    """Two automations driving one room co-operate."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, _ = await _setup(hass, _zone("Kitchen"))
    zone = _zone_id(_entry, "Kitchen")
    _light(hass, "light.a", area_id=area.id)

    await _record(registry, zone, "light.a", "ctx-automation-one", ASKED)
    await _record(registry, zone, "light.a", "ctx-automation-two", {"brightness": 120, "color_temp_kelvin": 2700})

    assert list(registry.all_records()) == ["light.a"]
    assert claim_field(registry, zone, "light.a", "latest", "context_id") == "ctx-automation-two"


async def test_an_unavailable_light_holding_a_claim_does_not_hold_a_zone_open(hass: HomeAssistant):
    """Anything not `on` is dark, so one dead entity can't hold a room open.
    The claim predates the listener, as after a restart."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, _ = await _setup(hass, _zone("Kitchen"))
    zone = _zone_id(_entry, "Kitchen")
    _light(hass, "light.a", area_id=area.id)
    _light(hass, "light.dead", area_id=area.id)
    for e in ("light.a", "light.dead"):
        await _record(registry, zone, e, "ctx-ours", ASKED)

    hass.states.async_set("light.dead", "unavailable", {})
    await hass.async_block_till_done()
    assert set(registry.all_records()) == {"light.a", "light.dead"}, "precondition: the claim survives"

    unsub = registry.async_start_listening(hass)
    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()

    assert registry.all_records() == {}
    unsub()


async def test_zones_release_independently(hass: HomeAssistant):
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    hall = ar.async_get(hass).async_get_or_create("Hall")
    _entry, registry, _ = await _setup(
        hass, _zone("Kitchen"), _zone("Hall")
    )
    _light(hass, "light.k", area_id=kitchen.id)
    _light(hass, "light.h", area_id=hall.id)
    await _record(registry, _zone_id(_entry, "Kitchen"), "light.k", "ctx-ours", ASKED)
    await _record(registry, _zone_id(_entry, "Hall"), "light.h", "ctx-ours", ASKED)
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.k", "off", {})
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.h"}
    unsub()


async def test_the_clear_button_clears_only_its_own_zone(hass: HomeAssistant):
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    hall = ar.async_get(hass).async_get_or_create("Hall")
    _entry, registry, added = await _setup(
        hass, _zone("Kitchen"), _zone("Hall")
    )
    _light(hass, "light.k", area_id=kitchen.id)
    _light(hass, "light.h", area_id=hall.id)
    await _record(registry, _zone_id(_entry, "Kitchen"), "light.k", "ctx-k", ASKED)
    await _record(registry, _zone_id(_entry, "Hall"), "light.h", "ctx-h", ASKED)

    kitchen_button = next(e for e in added if e.entity_id == "button.kitchen_flare_clear")
    assert kitchen_button.extra_state_attributes["tracked"] == 1
    await kitchen_button.async_press()

    assert list(registry.all_records()) == ["light.h"]


async def test_the_override_event_is_filed_under_the_zone(hass: HomeAssistant):
    """device_id puts the event in the zone device's Activity, and the zone's
    sensor as entity_id in a logbook card targeting the zone."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, added = await _setup(hass, _zone("Kitchen"))
    instance = zone_instances(entry)[0]
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers=instance.device_info["identifiers"], name="Kitchen"
    )
    tracker = next(e for e in added if hasattr(e, "claims"))
    # A real added entity has a registry_entry; this harness sets one.
    tracker.registry_entry = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, tracker.unique_id, config_entry=entry, device_id=device.id
    )

    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)

    _light(hass, "light.a", area_id=area.id)
    await _record(registry, _zone_id(entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()  # seeds without announcing
    assert events == []

    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["device_id"] == device.id
    assert events[0].data["entity_id"] == "sensor.kitchen_flare_overridden"
    assert events[0].data["light"] == "light.a"
    assert events[0].data["zone"] == "Kitchen"
    assert events[0].data["live"]["brightness"] == 12
    assert events[0].data["latest"]["target"] == ASKED


async def _back_online_at_a_stale_level(hass: HomeAssistant):
    """A zone with one light just back online, reporting a stale level
    before FLARE's resend lands."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, added = await _setup(hass, _zone("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)
    _light(hass, "light.a", area_id=area.id, state="unavailable")
    await _record(registry, _zone_id(entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()
    hass.states.async_set("light.a", "on", {"brightness": 10, "color_temp_kelvin": 6500}, context=Context())
    hass.data.setdefault(RECONNECTS, {})["light.a"] = hass.states.get("light.a").last_changed
    tracker._refresh_statuses()
    await hass.async_block_till_done()
    overridden = next(e for e in added if e.entity_id.endswith("_flare_overridden"))
    return tracker, events, overridden


async def test_a_light_back_online_is_not_shown_overridden_while_it_settles(hass: HomeAssistant):
    tracker, events, overridden = await _back_online_at_a_stale_level(hass)

    assert events == []
    assert overridden.native_value == 0
    await tracker.async_will_remove_from_hass()  # cancels its recheck


async def test_a_light_still_overridden_once_settled_is_announced_and_counted(hass: HomeAssistant):
    _tracker, events, overridden = await _back_online_at_a_stale_level(hass)
    refreshed: list = []
    async_dispatcher_connect(hass, SIGNAL_CLAIMS_UPDATED, lambda: refreshed.append(True))

    later = dt_util.utcnow() + RECONNECT_SETTLE + timedelta(seconds=2)
    with freeze_time(later, real_asyncio=True):
        async_fire_time_changed(hass, later)
        await hass.async_block_till_done()
        assert overridden.native_value == 1
    assert refreshed, "the count sensors are told to refresh"

    assert [e.data["light"] for e in events] == ["light.a"]


async def test_a_light_that_settles_to_what_flare_asked_for_is_never_announced(hass: HomeAssistant):
    tracker, events, overridden = await _back_online_at_a_stale_level(hass)
    hass.states.async_set("light.a", "on", ASKED, context=Context())
    tracker._refresh_statuses()

    later = dt_util.utcnow() + RECONNECT_SETTLE + timedelta(seconds=2)
    with freeze_time(later, real_asyncio=True):
        async_fire_time_changed(hass, later)
        await hass.async_block_till_done()
        assert overridden.native_value == 0

    assert events == []


async def test_a_light_set_again_after_an_override_is_not_announced(hass: HomeAssistant):
    """Churn, not news: neither taken nor anything else."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, added = await _setup(hass, _zone("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    _light(hass, "light.a", area_id=area.id)
    await _record(registry, _zone_id(entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()
    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()

    hass.states.async_set("light.a", "on", ASKED, context=Context())
    tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()

    assert events == []


async def test_a_zone_going_dark_says_it_cleared_its_lights(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, _ = await _setup(hass, _zone("Kitchen"))
    events: list = []
    hass.bus.async_listen("flare_lights_released", events.append)
    for light in ("light.a", "light.b"):
        _light(hass, light, area_id=area.id)
        await _record(registry, _zone_id(entry, "Kitchen"), light, f"ctx-{light}", ASKED)
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()
    assert events == [], "one light still on"
    hass.states.async_set("light.b", "off", {})
    await hass.async_block_till_done()
    unsub()

    assert [(e.data["lights"], e.data["zone"], e.data["entity_id"]) for e in events] == [
        (["light.a", "light.b"], "Kitchen", "sensor.kitchen_flare_controlled")
    ]


async def test_clear_says_it_cleared_but_claims_clear_is_silent(hass: HomeAssistant):
    """The service is the blueprint's bookkeeping, run as lights are handed off."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, added = await _setup(hass, _zone("Kitchen"))
    events: list = []
    hass.bus.async_listen("flare_lights_released", events.append)
    for light in ("light.a", "light.b"):
        _light(hass, light, area_id=area.id)
        await _record(registry, _zone_id(entry, "Kitchen"), light, f"ctx-{light}", ASKED)

    await registry.async_clear(_zone_id(entry, "Kitchen"), ["light.a"])
    await hass.async_block_till_done()
    assert events == []

    await next(e for e in added if e.entity_id == "button.kitchen_flare_clear").async_press()
    await hass.async_block_till_done()

    assert [e.data["lights"] for e in events] == [["light.b"]]


async def test_lights_a_zone_takes_are_announced_together(hass: HomeAssistant):
    """flare_lights_controlled: one entry for a room coming on, not one per
    bulb as each reports back, with the zone's device for its Activity."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, added = await _setup(hass, _zone("Kitchen"))
    instance = zone_instances(entry)[0]
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers=instance.device_info["identifiers"], name="Kitchen"
    )
    tracker = next(e for e in added if hasattr(e, "claims"))
    tracker.registry_entry = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, tracker.unique_id, config_entry=entry, device_id=device.id
    )
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    tracker._refresh_statuses()  # seeds without announcing

    for light in ("light.a", "light.b"):
        _light(hass, light, area_id=area.id)
        await _record(registry, _zone_id(entry, "Kitchen"), light, f"ctx-{light}", ASKED)
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
            "entity_id": "sensor.kitchen_flare_controlled",
            "zone": "Kitchen",
            "device_id": device.id,
        }
    ], "once, and not again for lights it already had"


async def test_lights_taken_only_to_switch_them_off_are_not_announced(hass: HomeAssistant):
    """A turn-off claims lights too; the room is dark, so nothing was taken."""
    area = ar.async_get(hass).async_get_or_create("Hall")
    entry, registry, added = await _setup(hass, _zone("Hall"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    tracker._refresh_statuses()

    _light(hass, "light.a", area_id=area.id, state="off")
    await _record(registry, _zone_id(entry, "Hall"), "light.a", "ctx-ours", {"state": "off"})
    tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()

    assert events == []


async def test_a_light_coming_back_online_is_not_announced_as_taken(hass: HomeAssistant):
    """As every light does after a restart: it was already the zone's."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, added = await _setup(hass, _zone("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    events: list = []
    hass.bus.async_listen("flare_lights_controlled", events.append)
    _light(hass, "light.a", area_id=area.id)
    await _record(registry, _zone_id(entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    hass.states.async_set("light.a", "unavailable", {}, context=Context())
    tracker._refresh_statuses()  # seeds: unavailable

    hass.states.async_set("light.a", "on", ASKED, context=Context())
    tracker._refresh_statuses()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=CONTROLLED_GATHER_SECONDS + 1))
    await hass.async_block_till_done()

    assert events == []


async def test_the_event_omits_device_id_when_there_is_no_device(hass: HomeAssistant):
    """Absent, not null."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, added = await _setup(hass, _zone("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))

    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)

    _light(hass, "light.a", area_id=area.id)
    await _record(registry, _zone_id(_entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()
    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert "device_id" not in events[0].data


async def test_counters_refresh_when_a_lights_live_state_changes(hass: HomeAssistant):
    """The counts depend on live state, which changes with no claim changing.
    Unavailable rather than off: off with someone else's claim is still
    overridden."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, added = await _setup(hass, _zone("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    overridden = next(e for e in added if e.entity_id.endswith("_flare_overridden"))

    _light(hass, "light.a", area_id=area.id)
    await _record(registry, _zone_id(_entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    assert overridden.native_value == 1

    refreshed: list = []
    async_dispatcher_connect(hass, SIGNAL_CLAIMS_UPDATED, lambda: refreshed.append(True))

    hass.states.async_set("light.a", "unavailable", {})
    await tracker.async_update()
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


def _notifications(hass: HomeAssistant) -> dict:
    return persistent_notification._async_get_or_create_notifications(hass)


class TestALightInTwoZones:
    """Each zone reads the other's writes as overrides, so it's surfaced as a
    warning notification."""

    async def test_writing_a_light_another_zone_holds_warns(self, hass: HomeAssistant):
        entry, registry, _ = await _setup(hass, _zone("Kitchen"), _zone("Hall"))
        _light(hass, "light.shared")
        await _record(registry, _zone_id(entry, "Kitchen"), "light.shared", "ctx-k", ASKED)

        await _record(registry, _zone_id(entry, "Hall"), "light.shared", "ctx-h", ASKED)

        notification = _notifications(hass)["flare_light_in_two_zones_light.shared"]
        assert "Hall and Kitchen zones" in notification["message"]

    async def test_a_dismissed_warning_stays_dismissed(self, hass: HomeAssistant):
        """The conflict re-records on every write; the warning comes once."""
        entry, registry, _ = await _setup(hass, _zone("Kitchen"), _zone("Hall"))
        _light(hass, "light.shared")
        await _record(registry, _zone_id(entry, "Kitchen"), "light.shared", "ctx-k", ASKED)
        await _record(registry, _zone_id(entry, "Hall"), "light.shared", "ctx-h", ASKED)
        persistent_notification.async_dismiss(hass, "flare_light_in_two_zones_light.shared")

        await _record(registry, _zone_id(entry, "Kitchen"), "light.shared", "ctx-k2", ASKED)

        assert _notifications(hass) == {}

    async def test_a_light_in_one_zone_raises_nothing(self, hass: HomeAssistant):
        entry, registry, _ = await _setup(hass, _zone("Kitchen"), _zone("Hall"))
        _light(hass, "light.k")
        _light(hass, "light.h")

        await _record(registry, _zone_id(entry, "Kitchen"), "light.k", "ctx-1", ASKED)
        await _record(registry, _zone_id(entry, "Kitchen"), "light.k", "ctx-2", ASKED)
        await _record(registry, _zone_id(entry, "Hall"), "light.h", "ctx-3", ASKED)

        assert _notifications(hass) == {}
