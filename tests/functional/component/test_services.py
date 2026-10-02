"""The services' contracts through a real HA: schemas, responses, zone
validation and registration. The planning logic itself is unit tested."""

from __future__ import annotations

import pytest
import voluptuous as vol
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.flare.const import DOMAIN
from custom_components.flare.services.handlers import async_unload_services
from tests.functional.component.harness import (
    CT,
    apply_lighting,
    claims_check,
    set_light,
)
from tests.support import COMPONENT


async def test_compute_curve_service_returns_expected_shape(setup_integration: HomeAssistant):
    hass = setup_integration
    result = await hass.services.async_call(
        DOMAIN,
        "compute_curve",
        {"morning": 0, "day": 100, "evening": 200, "night": 300, "at": 150},
        blocking=True,
        return_response=True,
    )
    assert result["phase"] == "Day"
    assert "brightness" in result
    assert "kelvin" in result
    assert isinstance(result["rgb_color"], list) and len(result["rgb_color"]) == 3


async def test_compute_lighting_groups_is_read_only(setup_integration: HomeAssistant):
    """Plans only; issues no light calls."""
    hass = setup_integration
    calls = async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    result = await hass.services.async_call(
        DOMAIN,
        "compute_lighting_groups",
        {
            "entities": ["light.a"],
            "brightness": 200,
            "color_temp_kelvin": 4000,
        },
        blocking=True,
        return_response=True,
    )

    assert result["groups"][0]["combined"] == ["light.a"]
    assert calls == []


async def test_apply_lighting_missing_brightness_raises(setup_integration: HomeAssistant):
    """Required, so a missing sensor attribute fails loudly rather than
    dimming everything."""
    hass = setup_integration
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    with pytest.raises(vol.Invalid):
        # Raw call: the helper would supply brightness.
        await hass.services.async_call(
            DOMAIN,
            "apply_lighting",
            {"entities": ["light.a"], "color_temp_kelvin": 3200, "transition": 2},
            blocking=True,
        )


async def test_apply_lighting_non_numeric_color_temp_kelvin_raises(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    with pytest.raises(vol.Invalid):
        await apply_lighting(hass, ['light.a'], brightness=180, color_temp_kelvin='not-a-number', transition=2)


async def test_apply_lighting_accepts_an_explicit_null_rgb_color(setup_integration: HomeAssistant):
    """A sensor that doesn't publish rgb_color renders a literal None."""
    hass = setup_integration
    turn_on_calls = async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    await apply_lighting(hass, ['light.a'], brightness=180, color_temp_kelvin=3200, rgb_color=None, transition=2)

    assert len(turn_on_calls) == 1


async def test_compute_lighting_groups_accepts_an_explicit_null_rgb_color(setup_integration: HomeAssistant):
    """The same, on compute_lighting_groups."""
    hass = setup_integration
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    result = await hass.services.async_call(
        DOMAIN,
        "compute_lighting_groups",
        {
            "entities": ["light.a"],
            "brightness": 200,
            "color_temp_kelvin": 4000,
            "rgb_color": None,
        },
        blocking=True,
        return_response=True,
    )

    assert result["groups"][0]["combined"] == ["light.a"]


async def test_compute_scene_coverage_requires_a_scene(setup_integration: HomeAssistant):
    """With no candidate scene there's nothing to ask."""
    hass = setup_integration
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "compute_scene_coverage",
            {"scope_entities": ["light.a"], "target_entities": ["light.a"]},
            blocking=True,
            return_response=True,
        )


async def test_compute_scene_coverage_reports_covered_and_uncovered_entities(setup_integration: HomeAssistant):
    hass = setup_integration
    hass.states.async_set("scene.night", "2024-01-01T00:00:00+00:00", {"entity_id": ["light.a"]})
    await hass.async_block_till_done()

    result = await hass.services.async_call(
        DOMAIN,
        "compute_scene_coverage",
        {
            "scene_entity_id": "scene.night",
            "scope_entities": ["light.a", "light.b"],
            "target_entities": ["light.a", "light.b"],
        },
        blocking=True,
        return_response=True,
    )
    assert result["scene_active"] is True
    assert result["covered_entities"] == ["light.a"]
    assert result["uncovered_entities"] == ["light.b"]


async def test_zone_device_id_rejects_a_nonexistent_device(setup_integration: HomeAssistant):
    """A bad device_id is a mistake, not "untracked"."""
    hass = setup_integration
    with pytest.raises(ServiceValidationError):
        await claims_check(hass, ["light.a"], device="not_a_real_device_id")


async def test_zone_device_id_rejects_a_device_that_isnt_a_zone(setup_integration: HomeAssistant):
    """Nor any device that isn't a zone."""
    hass = setup_integration
    entry = MockConfigEntry(domain="not_flare")
    entry.add_to_hass(hass)
    other_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("not_flare", "something_else")}
    )
    with pytest.raises(ServiceValidationError):
        await claims_check(hass, ["light.a"], device=other_device.id)


async def test_the_services_registered_are_exactly_the_ones_services_yaml_documents(setup_integration: HomeAssistant):
    """Against what's really registered, not a hand-written list."""
    documented = set(yaml.safe_load((COMPONENT / "services.yaml").read_text()))
    assert set(setup_integration.services.async_services_for_domain(DOMAIN)) == documented


async def test_unloading_the_services_removes_every_one_that_was_registered(setup_integration: HomeAssistant):
    hass = setup_integration
    assert hass.services.async_services_for_domain(DOMAIN), "precondition: services were registered"

    async_unload_services(hass)

    assert hass.services.async_services_for_domain(DOMAIN) == {}
