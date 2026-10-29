"""A fake house for the FLARE sandbox: the floors and rooms in
configuration.yaml, each room's bulbs, and a sensor whose occupancy and
illuminance are set by hand."""

from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

DOMAIN = "sandbox_house"
PLATFORMS = [
    Platform.LIGHT,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.MEDIA_PLAYER,
]

ROOM_SCHEMA = vol.Schema(
    {
        vol.Required("bulbs"): cv.positive_int,
        vol.Optional("icon"): cv.icon,
        vol.Optional("tv", default=False): cv.boolean,
    }
)
FLOOR_SCHEMA = vol.Schema(
    {vol.Optional("icon"): cv.icon, vol.Required("rooms"): {cv.string: ROOM_SCHEMA}}
)
CONFIG_SCHEMA = vol.Schema({DOMAIN: {cv.string: FLOOR_SCHEMA}}, extra=vol.ALLOW_EXTRA)


@dataclass(frozen=True)
class Room:
    name: str
    area_id: str
    bulbs: int
    tv: bool = False

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def bulb_device(self, number: int) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, f"{self.slug}_{number}")})

    def sensor_device(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, f"{self.slug}_sensor")})

    def tv_device(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, f"{self.slug}_tv")})

    def wall_switch_device(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, f"{self.slug}_wall_switch")})


def power_signal(room: Room, number: int) -> str:
    """Tells bulb `number` whether its own Power, or the room's Wall switch,
    is on: (source, on)."""
    return f"{DOMAIN}_power_{room.slug}_{number}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Create the floors and areas, then the entry holding the devices."""
    floors = fr.async_get(hass)
    areas = ar.async_get(hass)
    rooms = []
    for level, (floor_name, floor_conf) in enumerate(config.get(DOMAIN, {}).items()):
        floor = floors.async_get_floor_by_name(floor_name) or floors.async_create(
            floor_name, level=level, icon=floor_conf.get("icon")
        )
        for name, room in floor_conf["rooms"].items():
            area = areas.async_get_area_by_name(name) or areas.async_create(name)
            # Onboarding's default areas can exist first, without a floor.
            if area.floor_id is None or area.icon is None:
                area = areas.async_update(
                    area.id,
                    floor_id=area.floor_id or floor.floor_id,
                    icon=area.icon or room.get("icon"),
                )
            rooms.append(Room(name, area.id, room["bulbs"], room["tv"]))
    hass.data[DOMAIN] = rooms

    if not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT})
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Each bulb and each room's sensor is a device in its room."""
    devices = dr.async_get(hass)
    for room in hass.data[DOMAIN]:
        # Home Assistant puts the area in front of these in entity IDs:
        # light.kitchen_bulb_1, switch.kitchen_sensor_presence.
        wanted = [(f"Bulb {n}", "Bulb", room.bulb_device(n)) for n in range(1, room.bulbs + 1)]
        wanted.append(("Sensor", "Presence sensor", room.sensor_device()))
        wanted.append(("Wall switch", "Wall switch", room.wall_switch_device()))
        if room.tv:
            wanted.append(("TV", "TV", room.tv_device()))
        for name, model, info in wanted:
            device = devices.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers=info["identifiers"],
                name=name,
                manufacturer="Sandbox",
                model=model,
            )
            if device.area_id is None:
                devices.async_update_device(device.id, area_id=room.area_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

