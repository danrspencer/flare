"""The `recovered` trigger: a light becoming reachable again."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.functional.blueprint.harness import (
    add_flare_light,
    light,
    setup_room_automation,
)

# The trigger's `for:`.
HOLD = timedelta(seconds=5)


async def held(hass, frozen_time) -> None:
    """Past the trigger's hold. The frozen clock keeps the minute's tick out of it."""
    frozen_time.tick(HOLD + timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


class TestRecoveredTrigger:
    """docs/reference/blueprint.md's "A device regaining power after an outage".

    `recovered` only makes an ordinary tick run promptly. Freeing the light
    from its claim is claims.py's listener, tested in
    functional/component."""

    async def test_fires_and_resyncs_a_light_that_reconnects_on(self, hass, apply_lighting_calls, frozen_time):
        """Its value_template can't use `trigger`, which isn't in scope when arming."""
        light(hass, "light.a", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        light(hass, "light.a", "on", brightness=255)
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        assert any(c.data["entities"] == ["light.a"] and c.data["force"] is False for c in apply_lighting_calls)

    async def test_waits_for_the_light_to_boot_before_sending_it_anything(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """A bulb powered on at the wall misses a command sent the moment it
        reports in."""
        light(hass, "light.a", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        light(hass, "light.a", "on", brightness=255)
        await hass.async_block_till_done()
        frozen_time.tick(HOLD - timedelta(seconds=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        assert apply_lighting_calls == []

        await held(hass, frozen_time)
        assert any(c.data["entities"] == ["light.a"] for c in apply_lighting_calls)

    async def test_fires_for_a_light_found_through_a_floor(self, hass, apply_lighting_calls, frozen_time):
        """The trigger resolves the target itself, so floors need covering there too."""
        floor = fr.async_get(hass).async_create("Upstairs")
        area = ar.async_get(hass).async_get_or_create("Landing")
        ar.async_get(hass).async_update(area.id, floor_id=floor.floor_id)
        er.async_get(hass).async_get_or_create("light", "test", "a", suggested_object_id="a")
        er.async_get(hass).async_update_entity("light.a", area_id=area.id)
        light(hass, "light.a", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"floor_id": floor.floor_id})

        light(hass, "light.a", "on", brightness=255)
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        assert any(c.data["entities"] == ["light.a"] for c in apply_lighting_calls)

    async def test_does_not_turn_on_a_light_that_reconnects_off_in_a_dark_room(self, hass, apply_lighting_calls, frozen_time):
        """A light reconnecting off in a room with nothing on stays off."""
        light(hass, "light.a", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        for call in apply_lighting_calls:
            assert "light.a" not in call.data["entities"]

    async def test_a_plain_off_to_on_transition_does_not_fire_it(self, hass, apply_lighting_calls, frozen_time):
        """Only unavailable/unknown -> a real state arms it."""
        light(hass, "light.a", "off")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": "light.a"})

        light(hass, "light.a", "on", brightness=255)
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        assert apply_lighting_calls == []

    async def test_recovery_joins_the_ordinary_room_wide_tick_not_a_separate_call(self, hass, apply_lighting_calls, frozen_time):
        """Part of the room's single apply_lighting call, not a separate one."""
        light(hass, "light.recovering", "unavailable")
        light(hass, "light.sibling", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.recovering", "light.sibling"]})

        light(hass, "light.recovering", "on", brightness=255)
        light(hass, "light.sibling", "on", brightness=90, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        assert apply_lighting_calls
        assert set(apply_lighting_calls[-1].data["entities"]) == {"light.recovering", "light.sibling"}
        assert apply_lighting_calls[-1].data["force"] is False

    async def test_an_orphaned_permanently_unavailable_entity_does_not_veto_recovery(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """A permanently unavailable entity mustn't hold the trigger false."""
        light(hass, "light.orphan", "unavailable")  # never comes back
        light(hass, "light.real", "unavailable")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.orphan", "light.real"]})

        light(hass, "light.real", "on", brightness=255)
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        assert apply_lighting_calls, "orphaned entity must not block the room from ever recovering"
        assert "light.real" in apply_lighting_calls[-1].data["entities"]

    async def test_one_bulb_recovering_beside_available_siblings_does_not_fire(
        self, hass, apply_lighting_calls, frozen_time
    ):
        """The accepted blind spot: one bulb returning beside reachable siblings
        waits for the tick."""
        light(hass, "light.flaky", "unavailable")
        light(hass, "light.steady", "on", brightness=90, color_temp_kelvin=4000)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"entity_id": ["light.flaky", "light.steady"]})

        light(hass, "light.flaky", "on", brightness=255)
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        assert apply_lighting_calls == []


class TestRecoveredIgnoresFlares:
    async def test_a_flare_in_the_room_does_not_count_as_a_reachable_light(self, hass, apply_lighting_calls, frozen_time):
        """Counted, a flare would hold the trigger armed, so a light
        reconnecting would never fire it."""
        area = ar.async_get(hass).async_get_or_create("Lounge")
        er.async_get(hass).async_get_or_create("light", "test", "a", suggested_object_id="a")
        er.async_get(hass).async_update_entity("light.a", area_id=area.id)
        light(hass, "light.a", "unavailable")
        await add_flare_light(hass, "lounge_flare", area.id)
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"area_id": area.id})

        light(hass, "light.a", "on", brightness=255)
        await hass.async_block_till_done()
        await held(hass, frozen_time)

        assert any(c.data["entities"] == ["light.a"] for c in apply_lighting_calls)
