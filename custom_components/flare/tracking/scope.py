"""
Tracking scopes: the named records of which lights FLARE is driving, one
per "state" subentry of the Tracking config entry. (Code and older notes
call them state devices; the UI and docs call them tracking scopes.)

A scope is what override-protection claims belong to (see
write_tracking.py), and it is a real Home Assistant device so that a
service call can name it with `tracking_device_id`.

Deliberately separate from schedule/coordinator.py's ScheduleInstance: a
schedule says what values lights should take, a scope says whose claims a
light belongs to. A house can want one schedule per floor and one scope
per room, and forcing them to be the same object would make either choice
constrain the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import slugify

from ..const import CONF_TARGET, DOMAIN, SUBENTRY_TYPE_STATE


@dataclass
class StateInstance:
    """One state device - a named tracking scope, derived from a "state"
    subentry, owning the override-protection claims for whatever lights
    its target covers.

    Deliberately separate from ScheduleInstance: a schedule says *what
    values* lights should take, a state device says *whose* claims a
    light belongs to. A house can want one schedule per floor and one
    tracking scope per room, and forcing those to be the same object
    would make either choice constrain the other."""

    subentry_id: str
    prefix: str  # "<slug>_" - entity_id prefix, derived from the (required) name
    title: str
    target: dict  # area_id/device_id/entity_id lists, as a target selector returns

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.subentry_id)},
            name=self.title or "Adaptive Lighting State",
            entry_type=DeviceEntryType.SERVICE,
            # Lets services.yaml's tracking_device_id device selector filter
            # to tracking-scope devices specifically - ScheduleInstance's
            # own device_info shares this integration's DOMAIN, so a bare
            # `integration: flare` filter alone can't tell the two apart.
            model="Tracking Scope",
        )


def state_instances(entry: ConfigEntry) -> list[StateInstance]:
    """Every state device on this entry, sorted by title.

    The sort is load-bearing, not cosmetic: it is the tie-break when two
    scopes claim the same area, so which one wins is stable across
    restarts rather than depending on dict ordering (see
    write_tracking.py's resolution)."""
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
                target=dict(subentry.data.get(CONF_TARGET) or {}),
            )
        )
    return sorted(instances, key=lambda i: i.title)
