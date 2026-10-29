"""How FLARE's claim events read in the logbook: filed under the entity the
event names, which the logbook shows as the entry's name, so the message
names the room (the automation)."""

from homeassistant.core import Event, HomeAssistant

from custom_components.flare.logbook import async_describe_events


def _describers(hass: HomeAssistant) -> dict:
    found = {}
    async_describe_events(hass, lambda domain, event_type, describe: found.__setitem__(event_type, describe))
    return found


async def test_each_event_names_its_room_and_is_filed_under_its_entity(hass: HomeAssistant):
    """Taking lights and clearing them are one entry per room; only an
    override names a light."""
    hass.states.async_set("light.k1", "on", {"friendly_name": "Kitchen 1"})
    hass.states.async_set("automation.kitchen", "on", {"friendly_name": "Kitchen"})
    describe = _describers(hass)

    overridden = describe["flare_light_overridden"](
        Event(
            "flare_light_overridden",
            {
                "light": "light.k1",
                "entity_id": "sensor.flare_overridden_lights",
                "rooms": ["automation.kitchen"],
                "live": {"brightness": 12, "color_temp_kelvin": 6500},
                "latest": {"target": {"brightness": 255, "color_temp_kelvin": 4100}},
            },
        )
    )
    released = describe["flare_lights_released"](
        Event(
            "flare_lights_released",
            {"lights": ["light.k1", "light.k2"], "entity_id": "button.flare_clear", "room": "automation.kitchen"},
        )
    )
    controlled = describe["flare_lights_controlled"](
        Event(
            "flare_lights_controlled",
            {"lights": ["light.k1"], "controlled": 6, "entity_id": "sensor.flare_controlled_lights", "room": "automation.kitchen"},
        )
    )

    assert overridden == {
        "name": "Kitchen",
        "message": "Kitchen released Kitchen 1 to something else (last asked for 255/4100, found 12/6500)",
        "entity_id": "sensor.flare_overridden_lights",
    }
    assert controlled == {"name": "Kitchen", "message": "Kitchen is now controlling 6 lights", "entity_id": "sensor.flare_controlled_lights"}
    assert released == {"name": "Kitchen", "message": "Kitchen cleared 2 lights", "entity_id": "button.flare_clear"}


async def test_an_override_names_every_room_the_light_is_in(hass: HomeAssistant):
    hass.states.async_set("automation.kitchen", "on", {"friendly_name": "Kitchen"})
    describe = _describers(hass)

    overridden = describe["flare_light_overridden"](
        Event("flare_light_overridden", {"light": "light.k1", "rooms": ["automation.kitchen", "automation.gone"]})
    )

    assert overridden["name"] == "Kitchen, automation.gone"


async def test_a_release_with_nothing_asked_for_has_no_comparison(hass: HomeAssistant):
    describe = _describers(hass)

    released = describe["flare_light_overridden"](
        Event("flare_light_overridden", {"light": "light.gone", "entity_id": "sensor.flare_overridden_lights", "latest": {}})
    )

    assert released["message"] == "FLARE released light.gone to something else"


async def test_an_event_missing_its_fields_still_reads(hass: HomeAssistant):
    """One describer raising breaks the whole logbook."""
    describe = _describers(hass)

    overridden = describe["flare_light_overridden"](Event("flare_light_overridden", {}))
    released = describe["flare_lights_released"](Event("flare_lights_released", {}))

    assert overridden == {"name": "FLARE", "message": "FLARE released a light to something else"}
    assert released == {"name": "FLARE", "message": "FLARE cleared 0 lights"}


async def test_an_rgb_request_is_compared_with_the_lights_rgb(hass: HomeAssistant):
    """Not with its colour temperature, which a bulb reports alongside."""
    describe = _describers(hass)

    overridden = describe["flare_light_overridden"](
        Event(
            "flare_light_overridden",
            {
                "light": "light.k1",
                "live": {"brightness": 180, "color_temp_kelvin": 2702, "rgb_color": [255, 167, 88]},
                "latest": {"target": {"brightness": 180, "rgb_color": [255, 184, 123]}},
            },
        )
    )

    assert overridden["message"].endswith("(last asked for 180/[255, 184, 123], found 180/[255, 167, 88])")
