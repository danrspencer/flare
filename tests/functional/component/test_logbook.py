"""How FLARE's zone events read in the logbook: filed under the zone's
sensor, naming the light."""

from homeassistant.core import Event, HomeAssistant

from custom_components.flare.logbook import async_describe_events


def _describers(hass: HomeAssistant) -> dict:
    found = {}
    async_describe_events(hass, lambda domain, event_type, describe: found.__setitem__(event_type, describe))
    return found


async def test_each_event_names_its_zone_and_is_filed_under_the_zones_sensor(hass: HomeAssistant):
    """Taking lights and clearing them are one entry per zone; only an
    override names a light."""
    hass.states.async_set("light.k1", "on", {"friendly_name": "Kitchen 1"})
    describe = _describers(hass)

    overridden = describe["flare_light_overridden"](
        Event(
            "flare_light_overridden",
            {
                "light": "light.k1",
                "entity_id": "sensor.kitchen_flare_overridden",
                "zone": "Kitchen",
                "live": {"brightness": 12, "color_temp_kelvin": 6500},
                "latest": {"target": {"brightness": 255, "color_temp_kelvin": 4100}},
            },
        )
    )
    released = describe["flare_lights_released"](
        Event(
            "flare_lights_released",
            {"lights": ["light.k1", "light.k2"], "entity_id": "sensor.kitchen_flare_controlled", "zone": "Kitchen"},
        )
    )
    controlled = describe["flare_lights_controlled"](
        Event(
            "flare_lights_controlled",
            {"lights": ["light.k1"], "controlled": 6, "entity_id": "sensor.kitchen_flare_controlled", "zone": "Kitchen"},
        )
    )

    assert overridden == {
        "name": "Kitchen",
        "message": "released Kitchen 1 to something else (last asked for 255/4100, found 12/6500)",
        "entity_id": "sensor.kitchen_flare_overridden",
    }
    assert controlled == {"name": "Kitchen", "message": "now controlling 6 lights", "entity_id": "sensor.kitchen_flare_controlled"}
    assert released == {"name": "Kitchen", "message": "cleared 2 lights", "entity_id": "sensor.kitchen_flare_controlled"}


async def test_a_release_with_nothing_asked_for_has_no_comparison(hass: HomeAssistant):
    describe = _describers(hass)

    released = describe["flare_light_overridden"](
        Event("flare_light_overridden", {"light": "light.gone", "entity_id": "sensor.k_flare_overridden", "zone": "Kitchen", "latest": {}})
    )

    assert released["message"] == "released light.gone to something else"
