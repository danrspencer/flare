"""Zones: one per zone subentry of the Zones entry. Override-protection
claims belong to a zone, and it's a real device so a service call can
name it with `zone_device_id`. Separate from ScheduleInstance so a house
can have one schedule per floor and one zone per room."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import slugify

from ..const import DOMAIN, SUBENTRY_TYPE_ZONE


@dataclass
class ZoneInstance:
    """One zone, derived from its subentry."""

    subentry_id: str
    prefix: str  # "<slug>_" - entity_id prefix, derived from the (required) name
    title: str

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.subentry_id)},
            name=self.title,
            entry_type=DeviceEntryType.SERVICE,
            # Lets services.yaml's device selector tell zones apart from
            # schedule devices.
            model="Zone",
        )


def zone_instances(entry: ConfigEntry) -> list[ZoneInstance]:
    """Every zone on this entry, sorted by title."""
    instances = []
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_ZONE:
            continue
        slug = slugify(subentry.title)
        instances.append(
            ZoneInstance(
                subentry_id=subentry_id,
                prefix=f"{slug}_" if slug else "",
                title=subentry.title,
            )
        )
    return sorted(instances, key=lambda i: i.title)
