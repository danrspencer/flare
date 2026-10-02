"""Resolving Room Target into lights, occupancy sensors and a zone."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import label_registry as lr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from tests.functional.blueprint.harness import (
    light,
    occupancy,
    add_zone,
    setup_room_automation,
)


class TestRoomTargetResolution:
    """docs/blueprint.md#setting-up-a-room"""

    async def test_device_id_room_target_resolves_both_lights_and_occupancy_sensors(self, hass, apply_lighting_calls):
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)
        config_entry = MockConfigEntry(domain="test")
        config_entry.add_to_hass(hass)
        device = dev_reg.async_get_or_create(
            config_entry_id=config_entry.entry_id, identifiers={("test", "room_device")}
        )
        ent_reg.async_get_or_create("light", "test", "light_d", suggested_object_id="d", device_id=device.id)
        ent_reg.async_get_or_create(
            "binary_sensor", "test", "occ_d", suggested_object_id="occ_d", device_id=device.id
        )
        light(hass, "light.d", "on")
        occupancy(hass, "binary_sensor.occ_d", "on")
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"device_id": device.id})

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.d"]

    async def test_a_named_light_puts_its_device_siblings_in_scene_scope(
        self, hass, apply_lighting_calls, scene_turn_on_calls
    ):
        """A directly named light also pulls its device's siblings into scene
        scope."""
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)
        config_entry = MockConfigEntry(domain="test")
        config_entry.add_to_hass(hass)
        device = dev_reg.async_get_or_create(
            config_entry_id=config_entry.entry_id, identifiers={("test", "sibling_device")}
        )
        ent_reg.async_get_or_create("light", "test", "light_s", suggested_object_id="s", device_id=device.id)
        ent_reg.async_get_or_create(
            "switch", "test", "switch_s", suggested_object_id="s_aux", device_id=device.id
        )
        light(hass, "light.s", "on")
        hass.states.async_set("switch.s_aux", "off")
        # The scene covers the sibling, in scope only through light.s.
        hass.states.async_set(
            "scene.sibling_scene", "2024-01-01T00:00:00+00:00", {"entity_id": ["switch.s_aux"]}
        )
        await hass.async_block_till_done()

        await setup_room_automation(
            hass, room_target={"entity_id": "light.s"}, evening_scene="scene.sibling_scene"
        )

        hass.states.async_set("sensor.test_adaptive", "Evening", {"brightness": 150, "color_temp": 3000})
        await hass.async_block_till_done()

        assert scene_turn_on_calls and scene_turn_on_calls[-1].data["entity_id"] == ["scene.sibling_scene"]
        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.s"]

    async def test_area_id_room_target_resolves_both_lights_and_occupancy_sensors(
        self, hass, apply_lighting_calls
    ):
        area = ar.async_get(hass).async_get_or_create("test_room")
        entry = MockConfigEntry(domain="test")
        entry.add_to_hass(hass)
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("test", "light_device")}
        )
        dr.async_get(hass).async_update_device(device.id, area_id=area.id)
        ent_reg = er.async_get(hass)
        ent_reg.async_get_or_create(
            "light", "test", "light_a", suggested_object_id="a", device_id=device.id
        )
        ent_reg.async_get_or_create("binary_sensor", "test", "occ_a", suggested_object_id="occ")
        ent_reg.async_update_entity("binary_sensor.occ", area_id=area.id)

        light(hass, "light.a", "off")
        occupancy(hass, "binary_sensor.occ", "off")
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"area_id": area.id})

        occupancy(hass, "binary_sensor.occ", "on")
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["entities"] == ["light.a"]


    async def test_floor_room_target_resolves_the_lights_on_every_area_of_that_floor(
        self, hass, apply_lighting_calls
    ):
        floor = fr.async_get(hass).async_create("Upstairs")
        areas = ar.async_get(hass)
        for name, light_id in (("Landing", "landing"), ("Study", "study")):
            area = areas.async_get_or_create(name)
            areas.async_update(area.id, floor_id=floor.floor_id)
            er.async_get(hass).async_get_or_create("light", "test", light_id, suggested_object_id=light_id)
            er.async_get(hass).async_update_entity(f"light.{light_id}", area_id=area.id)
            light(hass, f"light.{light_id}", "on")
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"floor_id": floor.floor_id})

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls and sorted(apply_lighting_calls[-1].data["entities"]) == [
            "light.landing",
            "light.study",
        ]

    async def test_label_room_target_resolves_labelled_lights_devices_and_areas(
        self, hass, apply_lighting_calls
    ):
        label = lr.async_get(hass).async_create("Downlights").label_id
        ent_reg = er.async_get(hass)
        entry = MockConfigEntry(domain="test")
        entry.add_to_hass(hass)

        ent_reg.async_get_or_create("light", "test", "named", suggested_object_id="named")
        ent_reg.async_update_entity("light.named", labels={label})

        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("test", "labelled_device")}
        )
        dr.async_get(hass).async_update_device(device.id, labels={label})
        ent_reg.async_get_or_create("light", "test", "on_device", suggested_object_id="on_device", device_id=device.id)

        area = ar.async_get(hass).async_get_or_create("Hall")
        ar.async_get(hass).async_update(area.id, labels={label})
        ent_reg.async_get_or_create("light", "test", "in_area", suggested_object_id="in_area")
        ent_reg.async_update_entity("light.in_area", area_id=area.id)

        ent_reg.async_get_or_create("light", "test", "unlabelled", suggested_object_id="unlabelled")
        for entity_id in ("light.named", "light.on_device", "light.in_area", "light.unlabelled"):
            light(hass, entity_id, "on")
        await hass.async_block_till_done()

        await setup_room_automation(hass, room_target={"label_id": label})

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        assert apply_lighting_calls and sorted(apply_lighting_calls[-1].data["entities"]) == [
            "light.in_area",
            "light.named",
            "light.on_device",
        ]

class TestOverrideDetection:
    """docs/blueprint.md#why-didnt-my-light-change"""

    async def test_apply_lighting_names_the_picked_zone_whatever_area_the_lights_are_in(
        self, hass, apply_lighting_calls
    ):
        kitchen = ar.async_get(hass).async_get_or_create("Kitchen")
        add_zone(hass, kitchen.id, "kitchen")
        study = add_zone(hass, slug="study")
        er.async_get(hass).async_get_or_create("light", "test", "light_a", suggested_object_id="a")
        er.async_get(hass).async_update_entity("light.a", area_id=kitchen.id)
        light(hass, "light.a", "on")
        await hass.async_block_till_done()
        await setup_room_automation(hass, room_target={"area_id": kitchen.id}, zone=study)

        hass.states.async_set("sensor.test_adaptive", "Day", {"brightness": 210, "color_temp": 4000})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
        await hass.async_block_till_done()

        calls = apply_lighting_calls
        assert calls and calls[-1].data["zone_device_id"] == study
        assert calls[-1].data["force"] is False
