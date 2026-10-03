"""Flares: one per flare subentry of the Flares entry. A flare is a light
that sits over an automation: a bare turn-on runs the automation, a
turn-on with values goes to the automation's lights, and a turn-off
turns them off. Which lights those are is read live from the automation
(see automation.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify

from ..const import DOMAIN, SUBENTRY_TYPE_FLARE


@dataclass
class FlareInstance:
    """One flare, derived from its subentry."""

    subentry_id: str
    prefix: str  # "<slug>_" - entity_id prefix, derived from the name
    title: str
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def device_info(self) -> DeviceInfo:
        # Not a SERVICE device: it's put in a room's area, which is how
        # voice assistants and HomeKit place it.
        return DeviceInfo(
            identifiers={(DOMAIN, self.subentry_id)},
            name=self.title,
            model="Flare",
        )


def flare_instances(entry: ConfigEntry) -> list[FlareInstance]:
    """Every flare on this entry, sorted by title."""
    instances = []
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_FLARE:
            continue
        slug = slugify(subentry.title)
        instances.append(
            FlareInstance(
                subentry_id=subentry_id,
                prefix=f"{slug}_" if slug else "",
                title=subentry.title,
                config=dict(subentry.data),
            )
        )
    return sorted(instances, key=lambda i: i.title)
