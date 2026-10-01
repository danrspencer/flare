"""Tracking scopes (state devices): their entities hold the claims, the
counts, the Clear button, the override event and area placement. A light's
scope is whichever one a caller names, never resolved from its area."""

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.button import async_setup_entry as button_setup
from custom_components.flare.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_TRACKING,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_STATE,
)
from custom_components.flare.schedule.coordinator import ScheduleCoordinator, schedule_instances
from custom_components.flare.sensor import async_setup_entry as sensor_setup
from custom_components.flare.tracking.scope import state_instances
from custom_components.flare.tracking.write_tracking import SIGNAL_WRITE_TRACKING_UPDATED, ClaimRegistry

ASKED = {"brightness": 200, "color_temp_kelvin": 3000}


def _scope(title: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type=SUBENTRY_TYPE_STATE, title=title, unique_id=title.lower().replace(" ", "_"), data={}
    )


async def _setup(hass: HomeAssistant, *scopes: ConfigSubentryData):
    """An entry with these scopes and their real entities attached."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING}, subentries_data=list(scopes)
    )
    entry.add_to_hass(hass)
    registry = ClaimRegistry(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = registry

    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    await button_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    trackers = [e for e in added if hasattr(e, "claims")]
    for instance, tracker in zip(state_instances(entry), trackers):
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


def _scope_id(entry, title: str) -> str:
    return next(i.subentry_id for i in state_instances(entry) if i.title == title)


async def test_a_light_with_no_scope_named_is_not_tracked_and_stays_manageable(hass: HomeAssistant):
    """Only a caller naming the scope makes a light tracked."""
    _entry, registry, _ = await _setup(hass, _scope("Kitchen"))
    _light(hass, "light.elsewhere")

    await _record(registry, None, "light.elsewhere", "ctx-1", ASKED)
    assert registry.all_records() == {}
    assert registry.latest_context_id(None, "light.elsewhere") is None


async def test_a_write_before_the_scopes_entity_exists_is_dropped(hass: HomeAssistant):
    """Services exist before platforms, so this can really happen."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING},
        subentries_data=[_scope("Kitchen")],
    )
    entry.add_to_hass(hass)
    registry = ClaimRegistry(hass, entry)  # no entities registered yet
    _light(hass, "light.a", area_id=area.id)

    await _record(registry, _scope_id(entry, "Kitchen"), "light.a", "ctx-1", ASKED)

    assert registry.all_records() == {}


async def test_claims_live_on_the_tracking_entity_and_are_published_there(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, added = await _setup(hass, _scope("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    _light(hass, "light.a", area_id=area.id)

    await _record(registry, _scope_id(_entry, "Kitchen"), "light.a", "ctx-1", ASKED)

    # The registry mutated this very dict.
    assert "light.a" in tracker.claims
    assert registry.all_records()["light.a"] is tracker.claims["light.a"]
    assert tracker.native_value == 1
    assert tracker.extra_state_attributes["claims"]["light.a"]["latest"]["context_id"] == "ctx-1"
    assert "claims" in tracker._unrecorded_attributes


async def test_counters_split_one_scopes_lights_by_status(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, added = await _setup(hass, _scope("Kitchen"))
    controlled = next(e for e in added if e.entity_id.endswith("_flare_controlled"))
    overridden = next(e for e in added if e.entity_id.endswith("_flare_overridden"))

    scope = _scope_id(_entry, "Kitchen")
    ours = Context()
    _light(hass, "light.mine", area_id=area.id)
    _light(hass, "light.taken", area_id=area.id)
    await _record(registry, scope, "light.mine", ours.id, ASKED)
    await _record(registry, scope, "light.taken", "ctx-ours", ASKED)
    hass.states.async_set("light.mine", "on", ASKED, context=ours)
    hass.states.async_set("light.taken", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())

    assert controlled.native_value == 1
    assert overridden.native_value == 1
    assert overridden.extra_state_attributes["lights"] == ["light.taken"]
    assert controlled.extra_state_attributes["total_tracked"] == 2


async def test_two_callers_writing_one_light_share_the_scopes_claims(hass: HomeAssistant):
    """Two automations driving one room co-operate."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, _ = await _setup(hass, _scope("Kitchen"))
    scope = _scope_id(_entry, "Kitchen")
    _light(hass, "light.a", area_id=area.id)

    await _record(registry, scope, "light.a", "ctx-automation-one", ASKED)
    await _record(registry, scope, "light.a", "ctx-automation-two", {"brightness": 120, "color_temp_kelvin": 2700})

    assert list(registry.all_records()) == ["light.a"]
    assert registry.latest_context_id(scope, "light.a") == "ctx-automation-two"


async def test_an_unavailable_light_holding_a_claim_does_not_hold_a_scope_open(hass: HomeAssistant):
    """Anything not `on` is dark, so one dead entity can't hold a room open.
    The claim predates the listener, as after a restart."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, _ = await _setup(hass, _scope("Kitchen"))
    scope = _scope_id(_entry, "Kitchen")
    _light(hass, "light.a", area_id=area.id)
    _light(hass, "light.dead", area_id=area.id)
    for e in ("light.a", "light.dead"):
        await _record(registry, scope, e, "ctx-ours", ASKED)

    hass.states.async_set("light.dead", "unavailable", {})
    await hass.async_block_till_done()
    assert set(registry.all_records()) == {"light.a", "light.dead"}, "precondition: the claim survives"

    unsub = registry.async_start_listening(hass)
    hass.states.async_set("light.a", "off", {})
    await hass.async_block_till_done()

    assert registry.all_records() == {}
    unsub()


async def test_scopes_release_independently(hass: HomeAssistant):
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    hall = ar.async_get(hass).async_get_or_create("Hall")
    _entry, registry, _ = await _setup(
        hass, _scope("Kitchen"), _scope("Hall")
    )
    _light(hass, "light.k", area_id=kitchen.id)
    _light(hass, "light.h", area_id=hall.id)
    await _record(registry, _scope_id(_entry, "Kitchen"), "light.k", "ctx-ours", ASKED)
    await _record(registry, _scope_id(_entry, "Hall"), "light.h", "ctx-ours", ASKED)
    unsub = registry.async_start_listening(hass)

    hass.states.async_set("light.k", "off", {})
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.h"}
    unsub()


async def test_the_clear_button_clears_only_its_own_scope(hass: HomeAssistant):
    kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
    hall = ar.async_get(hass).async_get_or_create("Hall")
    _entry, registry, added = await _setup(
        hass, _scope("Kitchen"), _scope("Hall")
    )
    _light(hass, "light.k", area_id=kitchen.id)
    _light(hass, "light.h", area_id=hall.id)
    await _record(registry, _scope_id(_entry, "Kitchen"), "light.k", "ctx-k", ASKED)
    await _record(registry, _scope_id(_entry, "Hall"), "light.h", "ctx-h", ASKED)

    kitchen_button = next(e for e in added if e.entity_id == "button.kitchen_flare_clear")
    assert kitchen_button.extra_state_attributes["tracked"] == 1
    await kitchen_button.async_press()

    assert list(registry.all_records()) == ["light.h"]


async def test_the_override_event_carries_the_scopes_device_id(hass: HomeAssistant):
    """device_id puts the event in the scope device's Activity."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry, registry, added = await _setup(hass, _scope("Kitchen"))
    instance = state_instances(entry)[0]
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
    await _record(registry, _scope_id(entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    tracker._refresh_statuses()  # seeds without announcing
    assert events == []

    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    tracker._refresh_statuses()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["device_id"] == device.id
    assert events[0].data["scope"] == "Kitchen"
    assert events[0].data["live"]["brightness"] == 12
    assert events[0].data["latest"]["target"] == ASKED


async def test_the_event_omits_device_id_when_there_is_no_device(hass: HomeAssistant):
    """Absent, not null."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    _entry, registry, added = await _setup(hass, _scope("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))

    events: list = []
    hass.bus.async_listen("flare_light_overridden", events.append)

    _light(hass, "light.a", area_id=area.id)
    await _record(registry, _scope_id(_entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
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
    _entry, registry, added = await _setup(hass, _scope("Kitchen"))
    tracker = next(e for e in added if hasattr(e, "claims"))
    overridden = next(e for e in added if e.entity_id.endswith("_flare_overridden"))

    _light(hass, "light.a", area_id=area.id)
    await _record(registry, _scope_id(_entry, "Kitchen"), "light.a", "ctx-ours", ASKED)
    hass.states.async_set("light.a", "on", {"brightness": 12, "color_temp_kelvin": 6500}, context=Context())
    assert overridden.native_value == 1

    refreshed: list = []
    async_dispatcher_connect(hass, SIGNAL_WRITE_TRACKING_UPDATED, lambda: refreshed.append(True))

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
