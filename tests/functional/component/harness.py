"""A Zones entry with one zone ("Test Zone"), set up directly, and
helpers for calling its services.

async_setup_entry is called directly rather than through
hass.config_entries.async_setup(), which would also load the manifest's
http/frontend dependencies - the large frontend package these tests don't
need. For the same reason the claims sensors are attached through the
real sensor platform with a capturing async_add_entities; test_state_devices.py
and test_claim_persistence.py cover a properly added entity.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState, ConfigSubentryData
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare import async_setup_entry
from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_ZONES, SUBENTRY_TYPE_ZONE
from custom_components.flare.sensor import async_setup_entry as sensor_setup
from custom_components.flare.zone.instance import zone_instances
from custom_components.flare.zone.claims import ClaimRegistry

CT = ["color_temp"]
TEST_LIGHTS = ("light.a", "light.never_tracked", "light.recovering", "light.sibling")
UNSET = object()  # "use Test Zone", as opposed to an explicit zone_device_id=None


def test_area(hass: HomeAssistant):
    return ar.async_get(hass).async_get_or_create("Adaptive Test Area")


async def setup_zones_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    registry = er.async_get(hass)
    for entity_id in TEST_LIGHTS:
        created = registry.async_get_or_create("light", "test", entity_id, suggested_object_id=entity_id.split(".", 1)[1])
        registry.async_update_entity(created.entity_id, area_id=test_area(hass).id)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_ZONES},
        options=options or {},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_ZONE,
                title="Test Zone",
                unique_id="test_zone",
                data={},
            )
        ],
    )
    entry.add_to_hass(hass)
    # async_setup_entry forwards platforms, which requires LOADED.
    entry.mock_state(hass, ConfigEntryState.LOADED)
    assert await async_setup_entry(hass, entry)
    await hass.async_block_till_done()

    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    for instance, entity in zip(zone_instances(entry), [e for e in added if hasattr(e, "claims")]):
        entity.async_claims_changed = lambda: None
        claim_registry(hass).register(instance.subentry_id, entity)
        # The capturing add_entities doesn't register the device.
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers=instance.device_info["identifiers"], name=instance.title
        )
    return entry


def claim_registry(hass: HomeAssistant) -> ClaimRegistry:
    return next(v for v in hass.data[DOMAIN].values() if isinstance(v, ClaimRegistry))


def zones_entry(hass: HomeAssistant):
    return next(e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ZONES)


def zone_id(hass: HomeAssistant) -> str:
    """Test Zone's subentry_id, which the registry takes."""
    return next(iter(zones_entry(hass).subentries))


def zone_device_id(hass: HomeAssistant) -> str:
    """Test Zone's device_id, which the services take."""
    entry = zones_entry(hass)
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, zone_id(hass)), entry.entry_id)
    assert device is not None
    return device.id


def set_light(hass: HomeAssistant, entity_id: str, state: str, *, context: Context | None = None, **attrs) -> None:
    hass.states.async_set(entity_id, state, attrs, context=context)


async def apply_lighting(hass: HomeAssistant, entities: list[str], *, context: Context | None = None, **overrides):
    """apply_lighting at 200/3000 into Test Zone, unless overridden."""
    data = {
        "entities": entities,
        "brightness": 200,
        "color_temp_kelvin": 3000,
        "transition": 0,
        "zone_device_id": zone_device_id(hass),
        **overrides,
    }
    await hass.services.async_call(DOMAIN, "apply_lighting", data, blocking=True, context=context)


async def turn_off(hass: HomeAssistant, entities: list[str], *, context: Context | None = None, **overrides):
    data = {"entities": entities, "zone_device_id": zone_device_id(hass), **overrides}
    await hass.services.async_call(DOMAIN, "turn_off", data, blocking=True, context=context)


async def claims_check(hass: HomeAssistant, entities: list[str], *, device=UNSET) -> dict:
    device = zone_device_id(hass) if device is UNSET else device
    result = await hass.services.async_call(
        DOMAIN, "claims_check", {"entities": entities, "zone_device_id": device}, blocking=True, return_response=True
    )
    return result["results"]


async def claims_record(hass: HomeAssistant, entities: list[str], *, targets=None, context=None, device=UNSET):
    device = zone_device_id(hass) if device is UNSET else device
    data = {"entities": entities, "zone_device_id": device}
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
