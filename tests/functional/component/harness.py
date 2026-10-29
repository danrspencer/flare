"""The Settings entry, set up directly, and helpers for calling its
services as one room ("automation.test_room").

async_setup_entry is called directly rather than through
hass.config_entries.async_setup(), which would also load the manifest's
http/frontend dependencies - the large frontend package these tests don't
need.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare import async_setup_entry
from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SETTINGS
from custom_components.flare.tracking.claims import ClaimRegistry

CT = ["color_temp"]
TEST_LIGHTS = ("light.a", "light.never_tracked", "light.recovering", "light.sibling")
# The room the helpers write for; any string does, and an automation's
# entity_id is what the blueprint passes.
ROOM = "automation.test_room"
UNSET = object()  # "use ROOM", as opposed to an explicit room_id=None


def test_area(hass: HomeAssistant):
    return ar.async_get(hass).async_get_or_create("Adaptive Test Area")


async def setup_settings_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    registry = er.async_get(hass)
    for entity_id in TEST_LIGHTS:
        created = registry.async_get_or_create("light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1])
        registry.async_update_entity(created.entity_id, area_id=test_area(hass).id)

    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS}, options=options or {}, version=3, minor_version=2
    )
    entry.add_to_hass(hass)
    # async_setup_entry forwards platforms, which requires LOADED.
    entry.mock_state(hass, ConfigEntryState.LOADED)
    assert await async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    return entry


def claim_registry(hass: HomeAssistant) -> ClaimRegistry:
    return next(
        e.runtime_data for e in hass.config_entries.async_entries(DOMAIN) if isinstance(getattr(e, "runtime_data", None), ClaimRegistry)
    )


def claims_store(hass: HomeAssistant):
    """Where the claims and rooms are held."""
    return claim_registry(hass)


def settings_entry(hass: HomeAssistant):
    return next(e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SETTINGS)


def set_light(hass: HomeAssistant, entity_id: str, state: str, *, context: Context | None = None, **attrs) -> None:
    hass.states.async_set(entity_id, state, attrs, context=context)


async def apply_lighting(hass: HomeAssistant, entities: list[str], *, context: Context | None = None, **overrides):
    """apply_lighting at 200/3000 for ROOM, unless overridden."""
    data = {
        "entities": entities,
        "brightness": 200,
        "color_temp_kelvin": 3000,
        "transition": 0,
        "room_id": ROOM,
        **overrides,
    }
    await hass.services.async_call(DOMAIN, "apply_lighting", data, blocking=True, context=context)


async def turn_off(hass: HomeAssistant, entities: list[str], *, context: Context | None = None, **overrides):
    data = {"entities": entities, "room_id": ROOM, **overrides}
    await hass.services.async_call(DOMAIN, "turn_off", data, blocking=True, context=context)


async def claims_check(hass: HomeAssistant, entities: list[str]) -> dict:
    result = await hass.services.async_call(
        DOMAIN, "claims_check", {"entities": entities}, blocking=True, return_response=True
    )
    return result["results"]


async def claims_record(hass: HomeAssistant, entities: list[str], *, targets=None, context=None, room=ROOM):
    data = {"entities": entities, "room_id": room}
    if targets is not None:
        data["targets"] = targets
    return await hass.services.async_call(DOMAIN, "claims_record", data, blocking=True, context=context, return_response=True)


async def label_two_step(hass: HomeAssistant, entity_id: str) -> None:
    """Puts the no_combined_transition label on the entity itself."""
    domain, object_id = entity_id.split(".", 1)
    er.async_get(hass).async_get_or_create(domain, "test", object_id, suggested_object_id=object_id)
    er.async_get(hass).async_update_entity(entity_id, labels={"no_combined_transition"})


async def add_device_light(hass: HomeAssistant, entity_id: str, *, manufacturer: str, model: str) -> None:
    """A light on a real device with that manufacturer/model, no label."""
    domain, object_id = entity_id.split(".", 1)
    owner = MockConfigEntry(domain="test")
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("test", object_id)}, manufacturer=manufacturer, model=model, name=object_id
    )
    dr.async_get(hass).async_update_device(device.id, area_id=test_area(hass).id)
    er.async_get(hass).async_get_or_create(domain, "test", object_id, suggested_object_id=object_id, device_id=device.id)
