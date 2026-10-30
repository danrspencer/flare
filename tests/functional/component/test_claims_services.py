"""claims_check, claims_record, claims_clear and claims_override."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.core import Context, HomeAssistant

from custom_components.flare.const import (
    CONF_MIN_BRIGHTNESS_CHANGE,
    CONF_MIN_COLOR_TEMP_CHANGE,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import async_mock_service
from tests.support.claims import after_the_grace
from tests.functional.component.harness import (
    CT,
    claim_registry,
    claims_check,
    claims_record,
    ROOM,
    apply_lighting,
    set_light,
    setup_settings_entry,
)


async def test_claims_check_reports_untracked_for_a_brand_new_entity(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)

    results = await claims_check(hass, ["light.a"])

    assert results["light.a"] == {"blocked": False, "status": "untracked", "matched_via": None, "rooms": []}


async def test_claims_check_reports_an_unreachable_light_as_unavailable_not_overridden(
    setup_integration: HomeAssistant,
):
    """Claims restored at startup meet lights that haven't reconnected yet."""
    hass = setup_integration
    hass.states.async_set("light.a", "unavailable", {})
    await claims_record(hass, ["light.a"], targets={"light.a": {"brightness": 100, "color_temp_kelvin": 3000}})
    hass.states.async_set("light.a", "unknown", {}, context=Context())

    results = await claims_check(hass, ["light.a"])

    assert results["light.a"] == {"blocked": False, "status": "unavailable", "matched_via": None, "rooms": [ROOM]}


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
        "rooms": [ROOM],
    }

    # Someone else changes it - a different context, different values.
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=40, color_temp_kelvin=6000)

    results = await claims_check(hass, ["light.a"])
    assert results["light.a"] == {"blocked": True, "status": "mismatched", "matched_via": None, "rooms": [ROOM]}

    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000, context=our_context)
    results = await claims_check(hass, ["light.a"])
    assert results["light.a"] == {
        "blocked": False,
        "status": "controlled",
        "matched_via": "latest-context",
        "rooms": [ROOM],
    }


async def test_claims_check_names_every_room_a_light_is_in(setup_integration: HomeAssistant):
    """Whoever asks: claims are FLARE's, not the caller's."""
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    await claims_record(hass, ["light.a"], room="automation.other_room")
    await claims_record(hass, ["light.a"])

    results = await claims_check(hass, ["light.a"])
    assert results["light.a"]["rooms"] == sorted([ROOM, "automation.other_room"])


async def test_claims_record_requires_a_room(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "claims_record", {"entities": ["light.a"]}, blocking=True)


async def test_claims_record_records_everything_passed(setup_integration: HomeAssistant):
    """Every entity is recorded, wherever it is."""
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
    with after_the_grace():
        results = await claims_check(hass, ["light.a"])
    assert results["light.a"]["status"] == "overridden"

    await hass.services.async_call(
        DOMAIN, "claims_clear", {"entities": ["light.a"]}, blocking=True
    )

    results = await claims_check(hass, ["light.a"])
    assert results["light.a"] == {"blocked": False, "status": "untracked", "matched_via": None, "rooms": [ROOM]}


async def test_claims_clear_frees_every_entity_in_one_call(setup_integration: HomeAssistant):
    """Needs two tracked entities: a short-circuiting any(...pop...) would stop
    after the first."""
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    set_light(hass, "light.b", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    await claims_record(hass, ["light.a", "light.b"])
    assert "light.a" in claim_registry(hass).all_records()
    assert "light.b" in claim_registry(hass).all_records()

    result = await hass.services.async_call(
        DOMAIN,
        "claims_clear",
        {"entities": ["light.a", "light.b", "light.never_tracked"]},
        blocking=True,
        return_response=True,
    )

    assert result == {"cleared": ["light.a", "light.b"]}
    records = claim_registry(hass).all_records()
    assert "light.a" not in records
    assert "light.b" not in records


async def test_claims_clear_is_a_noop_for_an_untracked_entity(setup_integration: HomeAssistant):
    hass = setup_integration
    result = await hass.services.async_call(
        DOMAIN,
        "claims_clear",
        {"entities": ["light.never_tracked"]},
        blocking=True,
        return_response=True,
    )
    assert result == {"cleared": []}
    assert claim_registry(hass).all_records() == {}


async def _override(hass: HomeAssistant, entities: list[str]) -> dict:
    return await hass.services.async_call(
        DOMAIN,
        "claims_override",
        {"entities": entities, "room_id": ROOM},
        blocking=True,
        return_response=True,
    )


async def test_claims_override_marks_lights_overridden_whatever_their_state(setup_integration: HomeAssistant):
    """An untracked light, one FLARE drives, and an off one: each reads as
    someone else's, even with values FLARE asked for."""
    hass = setup_integration
    ours = Context()
    set_light(hass, "light.ours", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000, context=ours)
    await claims_record(hass, ["light.ours"], targets={"light.ours": {"brightness": 100}}, context=ours)
    set_light(hass, "light.untracked", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    set_light(hass, "light.off", "off")

    response = await _override(hass, ["light.ours", "light.untracked", "light.off"])

    assert response == {"overridden": ["light.ours", "light.untracked", "light.off"]}
    results = await claims_check(hass, ["light.ours", "light.untracked", "light.off"])
    assert {e: r["status"] for e, r in results.items()} == {
        "light.ours": "overridden",
        "light.untracked": "overridden",
        "light.off": "overridden",
    }


async def test_claims_clear_undoes_claims_override(setup_integration: HomeAssistant):
    hass = setup_integration
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000)
    await _override(hass, ["light.a"])

    await hass.services.async_call(
        DOMAIN, "claims_clear", {"entities": ["light.a"]}, blocking=True
    )

    assert (await claims_check(hass, ["light.a"]))["light.a"]["status"] == "untracked"


async def test_claims_override_needs_a_room(setup_integration: HomeAssistant):
    hass = setup_integration
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "claims_override", {"entities": ["light.a"]}, blocking=True)


class TestOverrideTolerances:
    """A light reporting within the Settings entry's tolerances of what FLARE
    asked for is still FLARE's: only a change someone would notice is an
    override. A call can pass its own."""

    async def _echo(self, hass: HomeAssistant, asked: dict, reported: dict) -> None:
        """Claimed at `asked`, then reported at `reported` under a fresh
        context, as a bulb does once HA has forgotten the write's context."""
        our_context = Context()
        set_light(hass, "light.a", "on", supported_color_modes=CT, context=our_context, **asked)
        await claims_record(hass, ["light.a"], targets={"light.a": asked}, context=our_context)
        set_light(hass, "light.a", "on", supported_color_modes=CT, **reported)

    # Seen live: 4294K asked, 4312K reported, about a mired apart. 192 is 4%
    # off 200.
    CASES = pytest.mark.parametrize(
        ("asked", "reported", "option"),
        [
            (
                {"brightness": 255, "color_temp_kelvin": 4294},
                {"brightness": 255, "color_temp_kelvin": 4312},
                CONF_MIN_COLOR_TEMP_CHANGE,
            ),
            (
                {"brightness": 200, "color_temp_kelvin": 3000},
                {"brightness": 192, "color_temp_kelvin": 3000},
                CONF_MIN_BRIGHTNESS_CHANGE,
            ),
        ],
        ids=["colour", "brightness"],
    )

    @CASES
    async def test_a_small_difference_is_still_controlled_by_default(
        self, hass: HomeAssistant, asked, reported, option
    ):
        await setup_settings_entry(hass)
        await self._echo(hass, asked, reported)
        turn_on = async_mock_service(hass, "light", "turn_on")

        assert (await claims_check(hass, ["light.a"]))["light.a"]["status"] == "controlled"
        await apply_lighting(hass, ["light.a"], brightness=100, color_temp_kelvin=2700)
        assert len(turn_on) == 1, "a controlled light should get the next write"

    @CASES
    async def test_the_entrys_option_sets_it(self, hass: HomeAssistant, asked, reported, option):
        await setup_settings_entry(hass, options={option: 0})
        await self._echo(hass, asked, reported)
        turn_on = async_mock_service(hass, "light", "turn_on")

        assert (await claims_check(hass, ["light.a"]))["light.a"]["blocked"]
        status, _via = claim_registry(hass).status("light.a")
        assert status == "mismatched", "the status sensors and events read the option too"
        await apply_lighting(hass, ["light.a"], brightness=100, color_temp_kelvin=2700)
        assert turn_on == [], "with no tolerance the light reads as someone else's"

    @CASES
    async def test_a_calls_own_tolerance_wins(self, hass: HomeAssistant, asked, reported, option):
        await setup_settings_entry(hass, options={option: 0})
        await self._echo(hass, asked, reported)

        result = await hass.services.async_call(
            DOMAIN, "claims_check", {"entities": ["light.a"], option: 10}, blocking=True, return_response=True
        )
        assert result["results"]["light.a"]["status"] == "controlled"

    async def test_the_fixed_tolerances_are_gone(self, hass: HomeAssistant):
        await setup_settings_entry(hass)
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                DOMAIN,
                "claims_check",
                {"entities": ["light.a"], "brightness_tolerance": 2},
                blocking=True,
                return_response=True,
            )
