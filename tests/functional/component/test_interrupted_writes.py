"""A write whose run stops part-way - a service call raising, or
`mode: restart` cancelling between a two-step bulb's steps - must not
lock the light out. Claims are recorded before dispatch, and a claim for
a write that never lands leaves the light matching its previous one.

The cancellation tests drive a real Script in mode: restart."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.script import SCRIPT_MODE_RESTART, Script

from custom_components.flare.const import DOMAIN
from tests.functional.component.harness import (
    CT,
    apply_lighting,
    claim_registry,
    label_two_step,
    zone_id,
    set_light,
    zone_device_id,
)
from tests.support.claims import claim_field


async def _status(hass: HomeAssistant, entity_id: str) -> dict:
    result = await hass.services.async_call(
        DOMAIN,
        "claims_check",
        {"entities": [entity_id], "zone_device_id": zone_device_id(hass)},
        blocking=True,
        return_response=True,
    )
    return result["results"][entity_id]


def _land(hass: HomeAssistant, entity_id: str, *, context: Context, brightness: int, kelvin: int) -> None:
    """Reflect a write into state under its call's context, as a real light does."""
    set_light(
        hass, entity_id, "on", supported_color_modes=CT, brightness=brightness, color_temp_kelvin=kelvin, context=context
    )


async def test_a_failing_group_does_not_lock_out_the_lights_that_did_land(setup_integration: HomeAssistant):
    hass = setup_integration
    fail = {"on": False}
    calls: list[list[str]] = []

    async def turn_on(call):
        ids = call.data["entity_id"]
        calls.append(ids if isinstance(ids, list) else [ids])
        if fail["on"] and "light.sibling" in calls[-1]:
            raise HomeAssistantError("device timed out")

    hass.services.async_register("light", "turn_on", turn_on)
    for e in ("light.a", "light.sibling"):
        set_light(hass, e, "off", supported_color_modes=CT)

    # Different brightnesses -> two groups -> two separate light.turn_on calls.
    both = ["light.a", "light.sibling"]

    c1 = Context()
    await apply_lighting(hass, both, brightness_levels={"light.sibling": 90}, brightness=180, color_temp_kelvin=3200, context=c1)
    _land(hass, "light.a", context=c1, brightness=180, kelvin=3200)
    _land(hass, "light.sibling", context=c1, brightness=90, kelvin=3200)

    # Tick 2: light.a's write succeeds, the sibling's group raises.
    fail["on"] = True
    c2 = Context()
    with pytest.raises(HomeAssistantError):
        await apply_lighting(hass, both, brightness_levels={"light.sibling": 100}, brightness=200, color_temp_kelvin=3000, context=c2)
    _land(hass, "light.a", context=c2, brightness=200, kelvin=3000)
    # The sibling's write never arrived: it is still exactly what tick 1 left.

    assert (await _status(hass, "light.a"))["status"] == "controlled"
    sibling = await _status(hass, "light.sibling")
    assert sibling["status"] == "controlled"
    assert sibling["matched_via"] == "observed-context"

    # And so tick 3 still drives light.a.
    fail["on"] = False
    calls.clear()
    await apply_lighting(hass, ["light.a"], brightness=100, color_temp_kelvin=4500, context=Context())
    assert calls == [["light.a"]]


async def test_a_write_that_never_arrives_leaves_the_light_matching_its_last_confirmed_state(
    setup_integration: HomeAssistant,
):
    hass = setup_integration
    fail = {"on": False}
    calls: list[dict] = []

    async def turn_on(call):
        calls.append(dict(call.data))
        if fail["on"]:
            raise HomeAssistantError("dropped")

    hass.services.async_register("light", "turn_on", turn_on)
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    c1 = Context()
    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=c1)
    _land(hass, "light.a", context=c1, brightness=180, kelvin=3200)

    fail["on"] = True
    with pytest.raises(HomeAssistantError):
        await apply_lighting(hass, ["light.a"], brightness=200, color_temp_kelvin=3000, context=Context())

    # Nothing changed on the bulb, so it still reads as ours, via the claim
    # tick 1 earned by being seen.
    status = await _status(hass, "light.a")
    assert status["status"] == "controlled"
    assert status["matched_via"] == "observed-context"

    fail["on"] = False
    calls.clear()
    await apply_lighting(hass, ["light.a"], brightness=200, color_temp_kelvin=3000, context=Context())
    assert len(calls) == 1


async def test_a_restart_during_a_two_step_write_does_not_lock_the_light_out(setup_integration: HomeAssistant):
    hass = setup_integration
    calls: list = []

    async def turn_on(call):
        calls.append(call)

    hass.services.async_register("light", "turn_on", turn_on)
    await label_two_step(hass, "light.a")
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    c1 = Context()
    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, transition=0, context=c1)
    _land(hass, "light.a", context=c1, brightness=180, kelvin=3200)
    calls.clear()

    script = Script(
        hass,
        cv.SCRIPT_SCHEMA(
            [
                {
                    "action": "flare.apply_lighting",
                    "data": {
                        "entities": ["light.a"],
                        "brightness": 100,
                        "color_temp_kelvin": 4500,
                        "transition": 2,  # two-step: a 1s sleep between the steps
                        "zone_device_id": zone_device_id(hass),
                    },
                }
            ]
        ),
        "restart repro",
        DOMAIN,
        script_mode=SCRIPT_MODE_RESTART,
    )

    # Run 1 sends its brightness-only step, which lands on the light under
    # that call's own context, as it would on a real bulb.
    run1 = hass.async_create_task(script.async_run(context=Context()))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if calls:
            break
    assert len(calls) == 1
    _land(hass, "light.a", context=calls[0].context, brightness=100, kelvin=3200)

    # A second trigger arrives while run 1 sleeps; mode: restart stops it.
    await script.async_run(context=Context())
    with pytest.raises(asyncio.CancelledError):
        await run1
    await hass.async_block_till_done()

    # Run 1 never sent its colour step, and run 2 finished the job rather than
    # finding the light overridden.
    assert len(calls) == 3
    assert calls[-1].data["color_temp_kelvin"] == 4500


async def test_the_claim_is_recorded_before_the_first_light_call_goes_out(setup_integration: HomeAssistant):
    hass = setup_integration
    registry = claim_registry(hass)
    zone = zone_id(hass)
    seen: list[tuple[str | None, str]] = []

    async def turn_on(call):
        seen.append((claim_field(registry, zone, "light.a", "latest", "context_id"), call.context.id))

    hass.services.async_register("light", "turn_on", turn_on)
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=Context())

    [(recorded, issued)] = seen
    assert recorded == issued


async def test_a_claim_is_only_promoted_once_a_bulb_has_actually_been_seen_in_it(setup_integration: HomeAssistant):
    """`observed` is replaced only by a state seen live."""
    hass = setup_integration
    registry = claim_registry(hass)
    zone = zone_id(hass)

    async def turn_on(call):
        pass

    hass.services.async_register("light", "turn_on", turn_on)
    set_light(hass, "light.a", "off", supported_color_modes=CT)
    baseline = hass.states.get("light.a").context.id

    # Tick 1 goes out but is never seen on the bulb.
    c1 = Context()
    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=c1)
    assert claim_field(registry, zone, "light.a", "observed", "context_id") == baseline
    assert claim_field(registry, zone, "light.a", "latest", "context_id") == c1.id

    # Tick 2: tick 1 was never seen, so it must NOT be promoted.
    c2 = Context()
    await apply_lighting(hass, ["light.a"], brightness=150, color_temp_kelvin=3000, context=c2)
    assert claim_field(registry, zone, "light.a", "observed", "context_id") == baseline
    assert claim_field(registry, zone, "light.a", "latest", "context_id") == c2.id

    # Tick 2 lands and is seen; the next write promotes it.
    _land(hass, "light.a", context=c2, brightness=150, kelvin=3000)
    c3 = Context()
    await apply_lighting(hass, ["light.a"], brightness=120, color_temp_kelvin=2700, context=c3)
    assert claim_field(registry, zone, "light.a", "observed", "context_id") == c2.id
    assert claim_field(registry, zone, "light.a", "latest", "context_id") == c3.id


async def test_turn_off_is_recorded_before_the_light_call_goes_out(setup_integration: HomeAssistant):
    hass = setup_integration
    registry = claim_registry(hass)
    zone = zone_id(hass)
    seen: list[tuple[str | None, str]] = []

    async def turn_off(call):
        seen.append((claim_field(registry, zone, "light.a", "latest", "context_id"), call.context.id))

    hass.services.async_register("light", "turn_off", turn_off)
    set_light(hass, "light.a", "on", supported_color_modes=CT, brightness=180, color_temp_kelvin=3200)

    await hass.services.async_call(
        DOMAIN,
        "turn_off",
        {"entities": ["light.a"], "zone_device_id": zone_device_id(hass)},
        blocking=True,
        context=Context(),
    )

    [(recorded, issued)] = seen
    assert recorded == issued


async def test_a_turn_off_that_fails_leaves_the_light_matching_its_last_confirmed_state(
    setup_integration: HomeAssistant,
):
    """The same, for a turn-off."""
    hass = setup_integration

    async def turn_on(call):
        pass

    async def turn_off(call):
        raise HomeAssistantError("device timed out")

    hass.services.async_register("light", "turn_on", turn_on)
    hass.services.async_register("light", "turn_off", turn_off)
    set_light(hass, "light.a", "off", supported_color_modes=CT)

    c1 = Context()
    await apply_lighting(hass, ["light.a"], brightness=180, color_temp_kelvin=3200, context=c1)
    _land(hass, "light.a", context=c1, brightness=180, kelvin=3200)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "turn_off",
            {"entities": ["light.a"], "zone_device_id": zone_device_id(hass)},
            blocking=True,
            context=Context(),
        )

    status = await _status(hass, "light.a")
    assert status["status"] == "controlled"
    assert status["matched_via"] == "observed-context"
