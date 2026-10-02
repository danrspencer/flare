"""Setting up a room automation from the real blueprint."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.support import BLUEPRINT_PATH

SENSOR = "sensor.test_adaptive"


async def setup_room_automation(
    hass: HomeAssistant,
    *,
    room_target: dict,
    zone: str | None = None,
    schedule: str | None = None,
    entity_id: str = "automation.room",
    alias: str = "room",
    **extra_inputs,
):
    """A room automation from the blueprint, following `schedule` (else one
    carrying SENSOR) in `zone` (else a fresh one)."""
    input_ = {
        "schedule": schedule or add_schedule(hass),
        "room_target": room_target,
        "zone": zone or add_zone(hass),
        **extra_inputs,
    }
    assert await async_setup_component(
        hass, "automation", {"automation": [{"alias": alias, "use_blueprint": {"path": BLUEPRINT_PATH, "input": input_}}]}
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is not None, f"{entity_id} failed to set up from the blueprint"


def light(hass: HomeAssistant, entity_id: str, state: str, **attrs) -> None:
    hass.states.async_set(entity_id, state, {"supported_color_modes": ["color_temp"], **attrs})


def occupancy(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state, {"device_class": "occupancy"})


def motion(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state, {"device_class": "motion"})


PHASES = ("Morning", "Day", "Evening", "Night")


def add_schedule(hass: HomeAssistant, sensor: str | None = SENSOR, slug: str = "test") -> str:
    """A schedule as the blueprint sees it: a FLARE device with model
    "Schedule", carrying `sensor` (or none) and a Phase that fires whenever
    the sensor's phase changes, as FLARE's own does. Returns its device_id."""
    entry = MockConfigEntry(domain="flare")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("flare", f"schedule_{slug}")}, name=slug, model="Schedule"
    )
    registry = er.async_get(hass)
    phase = registry.async_get_or_create(
        "event", "flare", f"{slug}_phase", suggested_object_id=f"{slug}_flare_phase", device_id=device.id
    ).entity_id
    hass.states.async_set(phase, "unknown", {"event_types": list(PHASES), "event_type": None})
    if sensor is None:
        return device.id
    # A state already set under this id would make the registry pick another,
    # so it's lifted off while the entity registers.
    existing = hass.states.get(sensor)
    if existing is not None:
        hass.states.async_remove(sensor)
    registry.async_get_or_create(
        "sensor", "flare", f"{slug}_sensor", suggested_object_id=sensor.split(".", 1)[1], device_id=device.id
    )
    if existing is not None:
        hass.states.async_set(sensor, existing.state, existing.attributes)

    @callback
    def _phase_changed(event) -> None:
        new, old = event.data["new_state"], event.data["old_state"]
        if new is None or new.state not in PHASES or (old is not None and old.state == new.state):
            return
        hass.states.async_set(phase, new.last_updated.isoformat(), {"event_types": list(PHASES), "event_type": new.state})

    async_track_state_change_event(hass, [sensor], _phase_changed)
    return device.id


def add_zone(hass: HomeAssistant, area_id: str | None = None, slug: str = "room") -> str:
    """A zone as the blueprint sees it: a FLARE device with model "Zone" and a
    Tick firing at the top of every minute, as FLARE's scheduler would.
    Returns its device_id."""
    entry = MockConfigEntry(domain="flare")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("flare", slug)}, name=slug, model="Zone"
    )
    if area_id is not None:
        dr.async_get(hass).async_update_device(device.id, area_id=area_id)
    tick = er.async_get(hass).async_get_or_create(
        "event", "flare", f"{slug}_tick", suggested_object_id=f"{slug}_flare_tick", device_id=device.id
    ).entity_id
    hass.states.async_set(tick, "unknown", {"event_types": ["flare_tick"], "event_type": None})

    @callback
    def _tick(now) -> None:
        hass.states.async_set(tick, now.isoformat(), {"event_types": ["flare_tick"], "event_type": "flare_tick"})

    async_track_time_change(hass, _tick, second=0)
    return device.id


def effective(call, entity_id):
    """The brightness a light ends up at: levels travel as brightness 255
    times a per-entity multiplier."""
    multipliers = call.data.get("brightness_multipliers") or {}
    return round(call.data["brightness"] * multipliers.get(entity_id, 1))
