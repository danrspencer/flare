"""Tracking scopes ("state devices" in the code): one per "state" subentry
of the Tracking entry. Override-protection claims belong to a scope, and
it's a real device so a service call can name it with
`tracking_device_id`. Separate from ScheduleInstance so a house can have
one schedule per floor and one scope per room."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import slugify

from ..const import DOMAIN, SUBENTRY_TYPE_STATE


@dataclass
class StateInstance:
    """One state device - a named tracking scope, derived from a "state"
    subentry."""

    subentry_id: str
    prefix: str  # "<slug>_" - entity_id prefix, derived from the (required) name
    title: str

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.subentry_id)},
            name=self.title or "Adaptive Lighting State",
            entry_type=DeviceEntryType.SERVICE,
            # Lets services.yaml's device selector tell scopes apart from
            # schedule devices.
            model="Zone",
        )


def state_instances(entry: ConfigEntry) -> list[StateInstance]:
    """Every state device on this entry, sorted by title."""
    instances = []
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_STATE:
            continue
        slug = slugify(subentry.title)
        instances.append(
            StateInstance(
                subentry_id=subentry_id,
                prefix=f"{slug}_" if slug else "",
                title=subentry.title,
            )
        )
    return sorted(instances, key=lambda i: i.title)
