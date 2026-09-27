"""Setting up a room automation from the real blueprint."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.support import BLUEPRINT_PATH

SENSOR = "sensor.test_adaptive"


async def setup_room_automation(
    hass: HomeAssistant, *, room_target: dict, entity_id: str = "automation.room", alias: str = "room", **extra_inputs
):
    input_ = {"adaptive_sensor": SENSOR, "room_target": room_target, **extra_inputs}
    assert await async_setup_component(
        hass, "automation", {"automation": [{"alias": alias, "use_blueprint": {"path": BLUEPRINT_PATH, "input": input_}}]}
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is not None, f"{entity_id} failed to set up from the blueprint"


def light(hass: HomeAssistant, entity_id: str, state: str, **attrs) -> None:
    hass.states.async_set(entity_id, state, {"supported_color_modes": ["color_temp"], **attrs})


def occupancy(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state, {"device_class": "occupancy"})


def register_tracking_scope(hass: HomeAssistant, area_id: str, slug: str) -> str:
    """Just enough of a tracking scope for the blueprint to find it: a
    device in the area with a sensor.<slug>_flare_tracking. Returns its
    device_id."""
    entry = MockConfigEntry(domain="flare")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("flare", slug)}, name=slug)
    dr.async_get(hass).async_update_device(device.id, area_id=area_id)
    er.async_get(hass).async_get_or_create(
        "sensor", "flare", f"{slug}_tracking", suggested_object_id=f"{slug}_flare_tracking", device_id=device.id
    )
    hass.states.async_set(f"sensor.{slug}_flare_tracking", "0")
    return device.id


def effective(call, entity_id):
    """The brightness a light ends up at: levels travel as brightness 255
    times a per-entity multiplier."""
    multipliers = call.data.get("brightness_multipliers") or {}
    return round(call.data["brightness"] * multipliers.get(entity_id, 1))
