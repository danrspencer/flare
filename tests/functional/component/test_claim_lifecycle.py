"""What happens to claims as lights change on their own: a zone going
dark, a light dropping and recovering, and pruning."""

from __future__ import annotations

from datetime import timedelta

from freezegun import freeze_time
from homeassistant.core import Context, HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.flare.const import DOMAIN
from custom_components.flare.zone.claims import STALE_RECORD_MAX_AGE_DAYS
from tests.functional.component.harness import (
    CT,
    apply_lighting,
    claim_registry,
    claims_check,
    claims_record,
    set_light,
    zone_device_id,
)


async def test_the_last_light_going_off_releases_the_whole_zone(setup_integration: HomeAssistant):
    """Nobody is using the room, so every light is free again."""
    hass = setup_integration
    our_context = Context()
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000, context=our_context)
    await claims_record(hass, ["light.a"], context=our_context)
    set_light(hass, "light.a", "off", context=Context(id="ctx-motion-off"))
    await hass.async_block_till_done()

    assert await claims_check(hass, ["light.a"]) == {
        "light.a": {"blocked": False, "status": "off", "matched_via": None, "zone": "Test Zone"}
    }


async def test_a_light_switched_off_by_hand_in_a_lit_room_is_left_off(setup_integration: HomeAssistant):
    """Switching one light off in a room still in use is a choice: the sibling
    holds the zone, so the claim stays. (The zone, not the physical room:
    an untracked light holds nothing open.)"""
    hass = setup_integration
    ours = Context()
    for e in ("light.a", "light.sibling"):
        set_light(hass, e, "on", supported_color_modes=CT, brightness=100, color_temp_kelvin=3000, context=ours)
    await claims_record(
        hass,
        ["light.a", "light.sibling"],
        targets={"light.a": {"brightness": 100, "color_temp_kelvin": 3000}},
        context=ours,
    )
    set_light(hass, "light.a", "off", context=Context(id="ctx-wall-switch"))
    await hass.async_block_till_done()

    results = await claims_check(hass, ["light.a"])
    assert results["light.a"]["status"] == "overridden"
    assert results["light.a"]["blocked"] is True


async def test_claim_is_cleared_when_light_goes_unavailable(setup_integration: HomeAssistant):
    """Its claim goes when it drops, so the reconnect - under a context we
    never issued - isn't read as an override."""
    hass = setup_integration
    turn_on_calls = async_mock_service(hass, "light", "turn_on")

    set_light(hass, "light.a", "off", supported_color_modes=CT)
    await apply_lighting(hass, ['light.a'], brightness=180, color_temp_kelvin=3200, transition=2)
    assert len(turn_on_calls) == 1

    set_light(hass, "light.a", "unavailable", supported_color_modes=CT)
    await hass.async_block_till_done()

    # Reconnects with a context we never issued.
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200)
    await hass.async_block_till_done()

    await apply_lighting(hass, ['light.a'], brightness=180, color_temp_kelvin=3200, transition=2)
    assert len(turn_on_calls) == 2


async def test_recovered_light_is_freed_while_an_unrelated_override_stays_protected(
    setup_integration: HomeAssistant,
):
    """Only the light that dropped is freed."""
    hass = setup_integration
    turn_on_calls = async_mock_service(hass, "light", "turn_on")

    for entity_id in ("light.recovering", "light.sibling"):
        set_light(hass, entity_id, "off", supported_color_modes=CT)

    our_context = Context()
    await apply_lighting(
        hass,
        ['light.recovering', 'light.sibling'],
        brightness=180,
        color_temp_kelvin=3200,
        transition=2,
        context=our_context,
    )
    assert len(turn_on_calls) == 1

    for entity_id in ("light.recovering", "light.sibling"):
        set_light(
            hass,
            entity_id,
            "on",
            supported_color_modes=CT,
            brightness=180,
            color_temp_kelvin=3200,
            context=our_context,
        )

    set_light(hass, "light.recovering", "unavailable", supported_color_modes=CT)
    await hass.async_block_till_done()
    set_light(
        hass, "light.recovering", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200
    )

    # Changed directly, never unavailable.
    set_light(
        hass, "light.sibling", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200
    )
    await hass.async_block_till_done()

    result = await hass.services.async_call(
        DOMAIN,
        "compute_lighting_groups",
        {
            "entities": ["light.recovering", "light.sibling"],
            "brightness": 180,
            "color_temp_kelvin": 3200,
            "zone_device_id": zone_device_id(hass),
        },
        blocking=True,
        return_response=True,
    )
    combined = result["groups"][0]["combined"]
    assert "light.recovering" in combined
    assert "light.sibling" not in combined


async def test_a_restart_style_unavailable_blip_does_not_clear_an_existing_record(
    setup_integration: HomeAssistant,
):
    """Every entity passes through unavailable/unknown on a restart with no
    prior state. Only a drop from a real on/off state clears a claim."""
    hass = setup_integration
    turn_on_calls = async_mock_service(hass, "light", "turn_on")

    set_light(hass, "light.a", "off", supported_color_modes=CT)
    our_context = Context()
    await apply_lighting(
        hass,
        ['light.a'],
        brightness=180,
        color_temp_kelvin=3200,
        transition=2,
        context=our_context,
    )
    assert len(turn_on_calls) == 1
    set_light(
        hass, "light.a", "on", supported_color_modes=CT, brightness=180, color_temp_kelvin=3200,
        context=our_context,
    )
    await hass.async_block_till_done()

    # A restart: the entity's state vanishes and reappears.
    hass.states.async_remove("light.a")
    await hass.async_block_till_done()
    set_light(hass, "light.a", "unavailable", supported_color_modes=CT)
    await hass.async_block_till_done()
    set_light(
        hass, "light.a", "on", supported_color_modes=CT, brightness=180, color_temp_kelvin=3200,
        context=our_context,
    )
    await hass.async_block_till_done()

    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200)
    await hass.async_block_till_done()

    result = await hass.services.async_call(
        DOMAIN,
        "compute_lighting_groups",
        {
            "entities": ["light.a"],
            "brightness": 180,
            "color_temp_kelvin": 3200,
            "zone_device_id": zone_device_id(hass),
        },
        blocking=True,
        return_response=True,
    )
    assert "light.a" not in result["groups"][0]["combined"]


async def test_prune_stale_removes_a_record_untouched_past_the_cutoff(setup_integration: HomeAssistant):
    hass = setup_integration
    async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    with freeze_time(dt_util.utcnow()) as frozen:
        await apply_lighting(
            hass,
            ['light.a'],
            brightness=180,
            color_temp_kelvin=3200,
            transition=2,
        )
        tracker = claim_registry(hass)
        assert "light.a" in tracker.all_records()

        frozen.move_to(dt_util.utcnow() + timedelta(days=STALE_RECORD_MAX_AGE_DAYS, hours=1))
        await tracker.async_prune_stale()

    assert "light.a" not in tracker.all_records()


async def test_prune_stale_leaves_a_recent_record_alone(setup_integration: HomeAssistant):
    hass = setup_integration
    async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    with freeze_time(dt_util.utcnow()) as frozen:
        await apply_lighting(
            hass,
            ['light.a'],
            brightness=180,
            color_temp_kelvin=3200,
            transition=2,
        )
        tracker = claim_registry(hass)

        frozen.move_to(dt_util.utcnow() + timedelta(hours=1))
        await tracker.async_prune_stale()

    assert "light.a" in tracker.all_records()


async def test_prune_stale_leaves_a_record_with_no_last_seen_alone(setup_integration: HomeAssistant):
    """Age can't be judged, so it's kept."""
    hass = setup_integration
    tracker = claim_registry(hass)
    tracker._stores[next(iter(tracker._stores))].claims["light.a"] = {  # this shape shouldn't occur naturally
        "observed": {"context_id": "ctx-old", "recorded_at": None, "target": None},
        "latest": None,
        "last_seen": None,
    }

    await tracker.async_prune_stale()

    assert "light.a" in tracker.all_records()


async def _groups(hass: HomeAssistant) -> list[str]:
    result = await hass.services.async_call(
        DOMAIN,
        "compute_lighting_groups",
        {"entities": ["light.a"], "brightness": 180, "color_temp_kelvin": 3200, "zone_device_id": zone_device_id(hass)},
        blocking=True,
        return_response=True,
    )
    return [e for group in result["groups"] for e in group["combined"]]


async def _light_back_online_and_a_lost_write(hass: HomeAssistant) -> None:
    """A bulb switched back on at the wall boots at its own default; FLARE
    writes to it straight away and the bulb never acts on it."""
    async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "unavailable", supported_color_modes=CT)
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=255, color_temp_kelvin=2702)
    await hass.async_block_till_done()
    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=Context())
    # The bulb reporting its boot state again, as Zigbee2MQTT does seconds later.
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=255, color_temp_kelvin=2701)
    await hass.async_block_till_done()


async def test_a_command_lost_as_a_light_comes_back_online_is_sent_again(setup_integration: HomeAssistant):
    """Nobody changed the light, so it isn't overridden."""
    hass = setup_integration
    await _light_back_online_and_a_lost_write(hass)

    assert (await claims_check(hass, ["light.a"]))["light.a"]["status"] == "untracked"
    assert await _groups(hass) == ["light.a"]


async def test_a_change_after_the_light_has_settled_still_counts_as_an_override(setup_integration: HomeAssistant):
    hass = setup_integration
    await _light_back_online_and_a_lost_write(hass)

    with freeze_time(dt_util.utcnow() + timedelta(seconds=31), real_asyncio=True):
        set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=2702)
        await hass.async_block_till_done()

        assert (await claims_check(hass, ["light.a"]))["light.a"]["status"] == "overridden"
        assert await _groups(hass) == []


async def test_a_change_soon_after_flares_write_landed_still_counts_as_an_override(setup_integration: HomeAssistant):
    """Once FLARE's write is seen to land, the light is FLARE's, however
    recently it came back."""
    hass = setup_integration
    async_mock_service(hass, "light", "turn_on")
    set_light(hass, "light.a", "unavailable", supported_color_modes=CT)
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=255, color_temp_kelvin=2702)
    await hass.async_block_till_done()
    ours = Context()
    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=ours)
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=180, color_temp_kelvin=3200, context=ours)
    await hass.async_block_till_done()

    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=90, color_temp_kelvin=3200)
    await hass.async_block_till_done()

    assert (await claims_check(hass, ["light.a"]))["light.a"]["status"] == "overridden"


async def _back_online_at_a_stale_level(hass: HomeAssistant) -> None:
    """A claim kept across a restart, and the light back online reporting
    something else before FLARE has written to it."""
    set_light(hass, "light.a", "unknown", supported_color_modes=CT)
    await claims_record(hass, ["light.a"], targets={"light.a": {"brightness": 180, "color_temp_kelvin": 3200}})
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=10, color_temp_kelvin=6500)
    await hass.async_block_till_done()


async def test_a_light_back_online_settles_before_it_counts_as_an_override(setup_integration: HomeAssistant):
    """Blocked meanwhile, like an override, so nothing writes over it."""
    hass = setup_integration
    await _back_online_at_a_stale_level(hass)

    result = (await claims_check(hass, ["light.a"]))["light.a"]
    assert (result["status"], result["blocked"]) == ("settling", True)
    assert await _groups(hass) == []


async def test_a_light_still_changed_once_settled_is_overridden(setup_integration: HomeAssistant):
    hass = setup_integration
    await _back_online_at_a_stale_level(hass)

    with freeze_time(dt_util.utcnow() + timedelta(seconds=31), real_asyncio=True):
        assert (await claims_check(hass, ["light.a"]))["light.a"]["status"] == "overridden"
