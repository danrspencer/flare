"""The `recovered` trigger: a light becoming reachable again."""

from __future__ import annotations



from tests.functional.blueprint.harness import (
    light,
    setup_room_automation,
)


class TestRecoveredTrigger:
    """docs/blueprint.md's "A device regaining power after an outage".

    `recovered` only makes an ordinary tick run promptly. Freeing the light
    from its claim is write_tracking's listener, tested in
    functional/component."""

    async def test_fires_and_resyncs_a_light_that_reconnects_on(self, hass, apply_lighting_calls):
        """Its value_template can't use `trigger`, which isn't in scope when arming."""
        light(hass, "light.a", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        light(hass, "light.a", "on", brightness=255)
        await hass.async_block_till_done()

        assert any(c.data["entities"] == ["light.a"] and c.data["force"] is False for c in apply_lighting_calls)

    async def test_does_not_turn_on_a_light_that_reconnects_off_in_a_dark_room(self, hass, apply_lighting_calls):
        """A light reconnecting off in a room with nothing on stays off."""
        light(hass, "light.a", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        light(hass, "light.a", "off")
        await hass.async_block_till_done()

        for call in apply_lighting_calls:
            assert "light.a" not in call.data["entities"]

    async def test_a_plain_off_to_on_transition_does_not_fire_it(self, hass, apply_lighting_calls):
        """Only unavailable/unknown -> a real state arms it."""
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        light(hass, "light.a", "on", brightness=255)
        await hass.async_block_till_done()

        assert apply_lighting_calls == []

    async def test_recovery_joins_the_ordinary_room_wide_tick_not_a_separate_call(self, hass, apply_lighting_calls):
        """Part of the room's single apply_lighting call, not a separate one."""
        light(hass, "light.recovering", "unavailable")
        light(hass, "light.sibling", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.recovering", "light.sibling"]})

        light(hass, "light.recovering", "on", brightness=255)
        light(hass, "light.sibling", "on", brightness=90, color_temp_kelvin=4000)
        await hass.async_block_till_done()

        assert apply_lighting_calls
        assert set(apply_lighting_calls[-1].data["entities"]) == {"light.recovering", "light.sibling"}
        assert apply_lighting_calls[-1].data["force"] is False

    async def test_an_orphaned_permanently_unavailable_entity_does_not_veto_recovery(
        self, hass, apply_lighting_calls
    ):
        """A permanently unavailable entity mustn't hold the trigger false."""
        light(hass, "light.orphan", "unavailable")  # never comes back
        light(hass, "light.real", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.orphan", "light.real"]})

        light(hass, "light.real", "on", brightness=255)
        await hass.async_block_till_done()

        assert apply_lighting_calls, "orphaned entity must not block the room from ever recovering"
        assert "light.real" in apply_lighting_calls[-1].data["entities"]

    async def test_one_bulb_recovering_beside_available_siblings_does_not_fire(
        self, hass, apply_lighting_calls
    ):
        """The accepted blind spot: one bulb returning beside reachable siblings
        waits for the tick."""
        light(hass, "light.flaky", "unavailable")
        light(hass, "light.steady", "on", brightness=90, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.flaky", "light.steady"]})

        light(hass, "light.flaky", "on", brightness=255)
        await hass.async_block_till_done()

        assert apply_lighting_calls == []
