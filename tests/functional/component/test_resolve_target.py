"""flare.resolve_target: the entities a target reaches, by Home Assistant's
own rule."""

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flare.const import DOMAIN
from custom_components.flare.services.targets import async_setup_target_services


@pytest.fixture(autouse=True)
def services(hass: HomeAssistant):
    async_setup_target_services(hass)


async def resolve(hass: HomeAssistant, **target) -> list[str]:
    response = await hass.services.async_call(DOMAIN, "resolve_target", target=target, blocking=True, return_response=True)
    return response["entities"]


def add_light(hass: HomeAssistant, object_id: str, **changes) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_or_create("light", "test", object_id, suggested_object_id=object_id).entity_id
    if changes:
        registry.async_update_entity(entity_id, **changes)
    return entity_id


async def test_an_area_leaves_out_its_hidden_and_categorised_lights(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Lounge").id
    add_light(hass, "lamp", area_id=area)
    add_light(hass, "hidden", area_id=area, hidden_by=er.RegistryEntryHider.USER)
    add_light(hass, "indicator", area_id=area, entity_category=EntityCategory.CONFIG)

    assert await resolve(hass, area_id=area) == ["light.lamp"]


async def test_a_device_leaves_out_its_hidden_and_categorised_lights(hass: HomeAssistant):
    entry = MockConfigEntry(domain="test")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", "switch")})
    add_light(hass, "load", device_id=device.id)
    add_light(hass, "led", device_id=device.id, entity_category=EntityCategory.CONFIG)
    add_light(hass, "spare", device_id=device.id, hidden_by=er.RegistryEntryHider.USER)

    assert await resolve(hass, device_id=device.id) == ["light.load"]


async def test_a_light_named_directly_is_kept_even_if_hidden(hass: HomeAssistant):
    hidden = add_light(hass, "hidden", hidden_by=er.RegistryEntryHider.USER)

    assert await resolve(hass, entity_id=hidden) == [hidden]


async def test_a_label_on_a_light_keeps_it_if_categorised_but_not_if_hidden(hass: HomeAssistant):
    label = lr.async_get(hass).async_create("Night").label_id
    add_light(hass, "indicator", labels={label}, entity_category=EntityCategory.CONFIG)
    add_light(hass, "hidden", labels={label}, hidden_by=er.RegistryEntryHider.USER)

    assert await resolve(hass, label_id=label) == ["light.indicator"]


async def test_entities_of_every_domain_are_returned(hass: HomeAssistant):
    area = ar.async_get(hass).async_get_or_create("Hall").id
    add_light(hass, "pendant", area_id=area)
    sensor = er.async_get(hass).async_get_or_create("binary_sensor", "test", "pir", suggested_object_id="hall_pir")
    er.async_get(hass).async_update_entity(sensor.entity_id, area_id=area)

    assert await resolve(hass, area_id=area) == ["binary_sensor.hall_pir", "light.pendant"]
