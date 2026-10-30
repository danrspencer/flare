"""The services' contracts through a real HA: schemas, responses, room
validation and registration. The planning logic itself is unit tested."""

from __future__ import annotations

import pytest
import voluptuous as vol
import yaml
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SETTINGS
from custom_components.flare.services.schedules import async_setup_schedule_services
from custom_components.flare.services.targets import async_setup_target_services
from tests.functional.component.harness import (
    CT,
    apply_lighting,
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


@pytest.mark.parametrize("brightness", [{}, {"brightness": None}], ids=["omitted", "null"])
async def test_apply_lighting_missing_brightness_raises(setup_integration: HomeAssistant, brightness):
    """Needed by any light without a level, so a missing sensor attribute
    fails loudly rather than dimming everything."""
    hass = setup_integration
    set_light(hass, "light.a", "off", supported_color_modes=CT)
    set_light(hass, "light.b", "off", supported_color_modes=CT)

    with pytest.raises(ServiceValidationError, match="light.b"):
        # Raw call: the helper would supply brightness.
        await hass.services.async_call(
            DOMAIN,
            "apply_lighting",
            {"entities": ["light.a", "light.b"], "brightness_levels": {"light.a": 50},
             "color_temp_kelvin": 3200, "transition": 2, **brightness},
            blocking=True,
        )


async def test_apply_lighting_needs_no_brightness_when_every_light_has_a_level(setup_integration: HomeAssistant):
    hass = setup_integration
    turn_on = async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    await hass.services.async_call(
        DOMAIN,
        "apply_lighting",
        {"entities": ["light.a"], "brightness_levels": {"light.a": 50}, "color_temp_kelvin": 3200, "transition": 2},
        blocking=True,
    )

    assert turn_on[-1].data["brightness"] == 50


async def test_apply_lighting_non_numeric_color_temp_kelvin_raises(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    with pytest.raises(vol.Invalid):
        await apply_lighting(hass, ['light.a'], brightness=180, color_temp_kelvin='not-a-number', transition=2)


@pytest.mark.parametrize(
    "values",
    [{"rgb_color": [256, 0, 0]}, {"rgb_color": [255, 0]}, {"color_temp_kelvin": -1}],
    ids=["rgb out of range", "rgb too short", "negative kelvin"],
)
async def test_apply_lighting_rejects_what_light_turn_on_would(setup_integration: HomeAssistant, values):
    hass = setup_integration
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    with pytest.raises(vol.Invalid):
        await apply_lighting(hass, ["light.a"], **{"brightness": 180, "color_temp_kelvin": 3200, "transition": 2, **values})


async def test_apply_lighting_clamps_brightness_and_transition_as_light_turn_on_does(setup_integration: HomeAssistant):
    hass = setup_integration
    turn_on = async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    await apply_lighting(hass, ["light.a"], brightness=300, color_temp_kelvin=3200, transition=-1)

    assert (turn_on[-1].data["brightness"], turn_on[-1].data["transition"]) == (255, 0)


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


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("compute_lighting_groups", {"brightness": 200, "color_temp_kelvin": 4000}),
        ("apply_lighting", {"brightness": 200, "color_temp_kelvin": 4000, "transition": 0}),
        ("turn_off", {}),
        ("claims_check", {}),
        ("claims_record", {"room_id": "automation.room"}),
        ("claims_clear", {}),
        ("claims_override", {"room_id": "automation.room"}),
    ],
)
async def test_the_lighting_and_claims_services_take_lights_only(setup_integration: HomeAssistant, service, data):
    hass = setup_integration
    responds = hass.services.supports_response(DOMAIN, service) is not SupportsResponse.NONE
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, service, {"entities": ["light.a", "switch.fan"], **data}, blocking=True, return_response=responds
        )


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


async def test_the_services_registered_are_exactly_the_ones_services_yaml_documents(setup_integration: HomeAssistant):
    """Against what's really registered, not a hand-written list. The
    schedule and target services come from async_setup, which this harness
    skips."""
    async_setup_schedule_services(setup_integration)
    async_setup_target_services(setup_integration)
    documented = set(yaml.safe_load((COMPONENT / "services.yaml").read_text()))
    assert set(setup_integration.services.async_services_for_domain(DOMAIN)) == documented


async def test_unloading_the_settings_entry_removes_every_service_it_registered(stub_entry_setup, hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS}, version=3, minor_version=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert hass.services.async_services_for_domain(DOMAIN), "precondition: services were registered"

    assert await hass.config_entries.async_unload(entry.entry_id)

    # Only those async_setup registers, which belong to no entry.
    assert set(hass.services.async_services_for_domain(DOMAIN)) == {"export_schedule", "import_schedule", "resolve_target"}
