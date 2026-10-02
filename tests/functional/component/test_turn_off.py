"""flare.turn_off: records its own off claim, then switches off."""

from __future__ import annotations

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.flare.const import DOMAIN
from tests.functional.component.harness import (
    apply_lighting,
    CT,
    claim_registry,
    claims_check,
    set_light,
    turn_off,
)


async def test_turn_off_turns_the_lights_off(setup_integration: HomeAssistant):
    hass = setup_integration
    off_calls = async_mock_service(hass, "light", "turn_off")
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=200, color_temp_kelvin=3000)

    await turn_off(hass, ["light.a"], transition=15)

    assert len(off_calls) == 1
    assert off_calls[0].data["entity_id"] == ["light.a"]
    assert off_calls[0].data["transition"] == 15


async def test_a_flare_turn_off_is_recognised_as_ours_even_once_its_context_has_expired(
    setup_integration: HomeAssistant,
):
    """The off lands under an unrelated context, as it does once HA's 5s
    context has expired, so only the recorded {"state": "off"} target
    says it was ours. A sibling stays on, or the dark zone would release
    the claim under test."""
    hass = setup_integration
    async_mock_service(hass, "light", "turn_on")
    async_mock_service(hass, "light", "turn_off")
    for entity in ("light.a", "light.sibling"):
        set_light(hass, entity, "off", supported_color_modes=CT)
    our_context = Context()
    await apply_lighting(hass, ["light.a", "light.sibling"], brightness=200, color_temp_kelvin=3000, context=our_context)
    for entity in ("light.a", "light.sibling"):
        set_light(
            hass, entity, "on", supported_color_modes=CT, brightness=200, color_temp_kelvin=3000, context=our_context
        )

    await turn_off(hass, ["light.a"])
    set_light(hass, "light.a", "off", supported_color_modes=CT)  # a fresh, unrelated context

    result = (await claims_check(hass, ["light.a"]))["light.a"]
    assert (result["status"], result["matched_via"]) == ("controlled", "latest-value")


async def test_turn_off_does_no_override_protection(setup_integration: HomeAssistant):
    """An emptied room goes dark, hand-set lights included."""
    hass = setup_integration
    off_calls = async_mock_service(hass, "light", "turn_off")
    set_light(hass, "light.a", "off", supported_color_modes=CT)
    our_context = Context()
    async_mock_service(hass, "light", "turn_on")
    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=our_context)
    set_light(
        hass, "light.a", "on", supported_color_modes=CT, brightness=180, color_temp_kelvin=3200, context=our_context
    )
    # Someone sets it by hand: overridden.
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=40, color_temp_kelvin=2200)

    await turn_off(hass, ["light.a"])

    assert [c.data["entity_id"] for c in off_calls] == [["light.a"]]


async def test_turn_off_without_a_zone_turns_off_and_records_nothing(setup_integration: HomeAssistant):
    hass = setup_integration
    off_calls = async_mock_service(hass, "light", "turn_off")
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=200, color_temp_kelvin=3000)

    await hass.services.async_call(
        DOMAIN, "turn_off", {"entities": ["light.a"], "zone_device_id": None}, blocking=True
    )

    assert len(off_calls) == 1
    assert claim_registry(hass).all_records() == {}


async def test_turn_off_rejects_a_device_that_is_not_a_zone(setup_integration: HomeAssistant):
    """Before anything is switched off."""
    hass = setup_integration
    off_calls = async_mock_service(hass, "light", "turn_off")
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=200, color_temp_kelvin=3000)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "turn_off",
            {"entities": ["light.a"], "zone_device_id": "not-a-real-device"},
            blocking=True,
        )

    assert off_calls == []


async def test_turn_off_with_no_entities_does_nothing(setup_integration: HomeAssistant):
    hass = setup_integration
    off_calls = async_mock_service(hass, "light", "turn_off")

    await turn_off(hass, [])

    assert off_calls == []
