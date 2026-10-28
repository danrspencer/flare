"""Each room light's status sensor: on the light's own device, saying what
claims_check says, kept through a rename, gone with the light."""

from datetime import timedelta
from unittest.mock import ANY

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, async_mock_service

from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SETTINGS
from custom_components.flare.diagnostics import async_get_config_entry_diagnostics
from custom_components.flare.tracking.override_protection import MISMATCH_GRACE

ROOM = "automation.kitchen"
SHOWING = {"brightness": 200, "color_temp_kelvin": 3000, "supported_color_modes": ["color_temp"], "color_mode": "color_temp"}


async def _set_up(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS}, unique_id=f"{DOMAIN}_tracking", version=3, minor_version=2
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "light", "turn_on")
    async_mock_service(hass, "light", "turn_off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _bulb(hass: HomeAssistant, object_id: str, *, on_device: bool = True) -> str:
    """A light another integration provides, on a device of its own."""
    owner = MockConfigEntry(domain="test")
    owner.add_to_hass(hass)
    device_id = None
    if on_device:
        device_id = dr.async_get(hass).async_get_or_create(
            config_entry_id=owner.entry_id, identifiers={("test", object_id)}, name=object_id.title()
        ).id
    er.async_get(hass).async_get_or_create(
        "light", "test", object_id, suggested_object_id=object_id, device_id=device_id, config_entry=owner
    )
    entity_id = f"light.{object_id}"
    hass.states.async_set(entity_id, "on", {**SHOWING, "brightness": 90, "friendly_name": object_id.title()})
    return entity_id


async def _apply(hass: HomeAssistant, entities: list[str], room_entities: list[str] | None = None) -> None:
    """Writes 200/3000 for ROOM, and has the bulbs report it under the
    write's context, as a real one would."""
    context = Context()
    await hass.services.async_call(
        DOMAIN,
        "apply_lighting",
        {
            "entities": entities,
            "brightness": 200,
            "color_temp_kelvin": 3000,
            "transition": 0,
            "room_id": ROOM,
            **({"room_entities": room_entities} if room_entities else {}),
        },
        blocking=True,
        context=context,
    )
    for entity_id in entities:
        hass.states.async_set(entity_id, "on", {**SHOWING, "friendly_name": entity_id}, context=context)
    await hass.async_block_till_done()


def _status_entity(hass: HomeAssistant, light: str) -> er.RegistryEntry | None:
    registry = er.async_get(hass)
    return next(
        (e for e in registry.entities.values() if e.platform == DOMAIN and e.translation_key == "status"
         and hass.states.get(e.entity_id) is not None and hass.states.get(e.entity_id).attributes.get("light") == light),
        None,
    )


async def test_a_room_light_gets_a_status_sensor_on_its_own_device(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    lamp = _bulb(hass, "lamp")

    await _apply(hass, [lamp])

    status = er.async_get(hass).async_get("sensor.lamp_flare_status")
    assert status is not None
    assert status.device_id == er.async_get(hass).async_get(lamp).device_id
    assert hass.states.get("sensor.lamp_flare_status").state == "controlled"
    assert hass.states.get("sensor.lamp_flare_status").attributes["rooms"] == [ROOM]


async def test_every_light_a_room_names_gets_one_even_before_it_is_written(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    lamp, spot = _bulb(hass, "lamp"), _bulb(hass, "spot")

    await _apply(hass, [lamp], room_entities=[lamp, spot])

    assert hass.states.get("sensor.spot_flare_status").state == "untracked"


async def test_a_light_changed_by_hand_reads_overridden_once_the_grace_has_passed(
    stub_entry_setup, hass: HomeAssistant, frozen_time
):
    await _set_up(hass)
    lamp = _bulb(hass, "lamp")
    await _apply(hass, [lamp])

    hass.states.async_set(lamp, "on", {**SHOWING, "brightness": 20}, context=Context())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lamp_flare_status").state == "mismatched"

    frozen_time.tick(MISMATCH_GRACE + timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lamp_flare_status").state == "overridden"


async def test_it_is_unavailable_while_its_light_is(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    lamp = _bulb(hass, "lamp")
    await _apply(hass, [lamp])

    hass.states.async_set(lamp, "unavailable")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.lamp_flare_status").state == "unavailable"


async def test_a_light_without_a_device_gets_a_sensor_named_after_it(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    group = _bulb(hass, "downstairs", on_device=False)

    await _apply(hass, [group])

    state = hass.states.get("sensor.downstairs_flare_status")
    assert state.state == "controlled"
    assert state.name == "Downstairs FLARE status"


async def test_it_follows_its_light_through_a_rename(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    lamp = _bulb(hass, "lamp")
    await _apply(hass, [lamp])

    er.async_get(hass).async_update_entity(lamp, new_entity_id="light.reading_lamp")
    hass.states.async_remove(lamp)
    hass.states.async_set("light.reading_lamp", "on", {**SHOWING, "brightness": 90})
    await _apply(hass, ["light.reading_lamp"])

    state = hass.states.get("sensor.lamp_flare_status")
    assert state.attributes["light"] == "light.reading_lamp"
    assert state.state == "controlled"
    assert _status_entity(hass, "light.reading_lamp").entity_id == "sensor.lamp_flare_status"


async def test_it_goes_with_its_light(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    lamp = _bulb(hass, "lamp")
    await _apply(hass, [lamp])

    er.async_get(hass).async_remove(lamp)
    await hass.async_block_till_done()

    assert er.async_get(hass).async_get("sensor.lamp_flare_status") is None


async def test_it_comes_back_after_a_reload_with_no_claims_left(stub_entry_setup, hass: HomeAssistant):
    entry = await _set_up(hass)
    lamp = _bulb(hass, "lamp")
    await _apply(hass, [lamp])
    await hass.services.async_call(DOMAIN, "claims_clear", {"entities": [lamp]}, blocking=True)
    hass.states.async_set(lamp, "off", {"friendly_name": "Lamp"})

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.lamp_flare_status").state == "off"


async def test_it_follows_a_light_flare_holds_nothing_on(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    lamp, spot = _bulb(hass, "lamp"), _bulb(hass, "spot")
    await _apply(hass, [lamp], room_entities=[lamp, spot])

    hass.states.async_set(spot, "off", {"friendly_name": "Spot"})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.spot_flare_status").state == "off"


async def test_the_sensor_that_held_the_claims_before_is_removed(stub_entry_setup, hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS}, unique_id=f"{DOMAIN}_tracking", version=3, minor_version=2
    )
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_claims", suggested_object_id="flare_claims", config_entry=entry
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert er.async_get(hass).async_get("sensor.flare_claims") is None


async def test_it_says_what_flare_last_asked_for_and_whether_flare_holds_it(stub_entry_setup, hass: HomeAssistant):
    await _set_up(hass)
    lamp, spot = _bulb(hass, "lamp"), _bulb(hass, "spot")

    await _apply(hass, [lamp], room_entities=[lamp, spot])

    lamp_state = hass.states.get("sensor.lamp_flare_status")
    assert lamp_state.attributes["asked"] == {"brightness": 200, "color_temp_kelvin": 3000}
    assert lamp_state.attributes["claimed"] is True
    spot_state = hass.states.get("sensor.spot_flare_status")
    assert (spot_state.attributes["asked"], spot_state.attributes["claimed"]) == (None, False)


async def test_diagnostics_has_every_claim_and_room(stub_entry_setup, hass: HomeAssistant):
    entry = await _set_up(hass)
    lamp = _bulb(hass, "lamp")
    await _apply(hass, [lamp])

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert set(diagnostics["claims"]) == {lamp}
    assert diagnostics["rooms"] == {ROOM: {"lights": [lamp], "last_seen": ANY}}
