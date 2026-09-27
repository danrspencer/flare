"""claims_check, claims_record and claims_clear."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.core import Context, HomeAssistant

from custom_components.flare.const import DOMAIN
from tests.functional.component.harness import (
    CT,
    claim_registry,
    claims_check,
    claims_record,
    set_light,
    tracking_device_id,
)


async def test_claims_check_reports_untracked_for_a_brand_new_entity(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)

    results = await claims_check(hass, ["light.a"])

    assert results["light.a"] == {"blocked": False, "status": "untracked", "matched_via": None, "scope": "Test Scope"}


async def test_claims_check_and_claims_record_round_trip(setup_integration: HomeAssistant):
    """Used together, with no apply_lighting, as an independent automation would."""
    hass = setup_integration
    our_context = Context()
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000, context=our_context)

    await claims_record(
        hass, ["light.a"], targets={"light.a": {"brightness": 100, "color_temp_kelvin": 3000}}, context=our_context
    )

    # Under the same context: ours. First-ever write, so both claims share the
    # context; latest is checked first.
    results = await claims_check(hass, ["light.a"])
    assert results["light.a"] == {
        "blocked": False,
        "status": "controlled",
        "matched_via": "latest-context",
        "scope": "Test Scope",
    }

    # Someone else changes it - a different context, different values.
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=40, color_temp_kelvin=6000)

    results = await claims_check(hass, ["light.a"])
    assert results["light.a"] == {"blocked": True, "status": "overridden", "matched_via": None, "scope": "Test Scope"}

    # Any caller naming the same scope shares its claims.
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000, context=our_context)
    results = await claims_check(hass, ["light.a"])
    assert results["light.a"] == {
        "blocked": False,
        "status": "controlled",
        "matched_via": "latest-context",
        "scope": "Test Scope",
    }


async def test_claims_check_echoes_back_whatever_scope_it_was_given(setup_integration: HomeAssistant):
    """It echoes the caller's scope, whatever the light's area."""
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    hass.states.async_set("light.elsewhere", "on", {"brightness": 100, "color_temp_kelvin": 3000})

    results = await claims_check(hass, ["light.a", "light.elsewhere"])
    assert results["light.a"]["scope"] == "Test Scope"
    assert results["light.elsewhere"]["scope"] == "Test Scope"


async def test_claims_check_requires_a_scope(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    with pytest.raises(vol.Invalid):
        await claims_check(hass, ["light.a"], device=None)


async def test_claims_record_requires_a_scope(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    with pytest.raises(vol.Invalid):
        await claims_record(hass, ["light.a"], device=None)


async def test_claims_record_records_everything_passed_once_a_scope_is_given(setup_integration: HomeAssistant):
    """Every entity is recorded into the named scope, wherever it is."""
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    hass.states.async_set("light.elsewhere", "on", {"brightness": 100, "color_temp_kelvin": 3000})

    result = await claims_record(hass, ["light.a", "light.elsewhere"])

    assert sorted(result["recorded"]) == ["light.a", "light.elsewhere"]


async def test_claims_check_does_not_take_force(setup_integration: HomeAssistant):
    """Forcing makes every answer "not blocked", so it isn't accepted."""
    hass = setup_integration
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "claims_check",
            {"entities": ["light.a"], "force": True},
            blocking=True,
            return_response=True,
        )


async def test_claims_clear_frees_a_light_stuck_overridden(setup_integration: HomeAssistant):
    """The escape hatch for a light stuck "overridden": after clearing, it's
    unclaimed."""
    hass = setup_integration
    our_context = Context()
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000, context=our_context)
    await claims_record(hass, ["light.a"], context=our_context)
    # Different value, different context: overridden.
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=40, color_temp_kelvin=6000)
    results = await claims_check(hass, ["light.a"])
    assert results["light.a"]["status"] == "overridden"

    await hass.services.async_call(
        DOMAIN, "claims_clear", {"entities": ["light.a"], "tracking_device_id": tracking_device_id(hass)}, blocking=True
    )

    results = await claims_check(hass, ["light.a"])
    assert results["light.a"] == {"blocked": False, "status": "untracked", "matched_via": None, "scope": "Test Scope"}


async def test_claims_clear_frees_every_entity_in_one_call(setup_integration: HomeAssistant):
    """Needs two tracked entities: a short-circuiting any(...pop...) would stop
    after the first."""
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    set_light(hass, "light.b", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    await claims_record(hass, ["light.a", "light.b"])
    assert "light.a" in claim_registry(hass).all_records()
    assert "light.b" in claim_registry(hass).all_records()

    await hass.services.async_call(
        DOMAIN,
        "claims_clear",
        {"entities": ["light.a", "light.b"], "tracking_device_id": tracking_device_id(hass)},
        blocking=True,
    )

    records = claim_registry(hass).all_records()
    assert "light.a" not in records
    assert "light.b" not in records


async def test_claims_clear_requires_a_scope(setup_integration: HomeAssistant):
    hass = setup_integration
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "claims_clear", {"entities": ["light.never_tracked"]}, blocking=True, return_response=True
        )


async def test_claims_clear_is_a_noop_for_an_untracked_entity_within_a_real_scope(setup_integration: HomeAssistant):
    hass = setup_integration
    result = await hass.services.async_call(
        DOMAIN,
        "claims_clear",
        {"entities": ["light.never_tracked"], "tracking_device_id": tracking_device_id(hass)},
        blocking=True,
        return_response=True,
    )
    assert result == {"cleared": ["light.never_tracked"]}
    assert claim_registry(hass).all_records() == {}
