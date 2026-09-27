"""A per-zone "Tick" event entity, fired by the zone scheduler (see
tracking/ticker.py). The blueprint listens for it through Lights &
Occupancy, so it has no entity_category: target expansion through an
area or device skips categorised entities."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_TYPE_TICK
from .tracking.scope import StateInstance, state_instances
from .tracking.ticker import TickScheduler


def ticks_key(entry: ConfigEntry) -> str:
    """The scheduler's key in hass.data[DOMAIN]."""
    return f"{entry.entry_id}_ticks"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    scheduler: TickScheduler = hass.data[DOMAIN][ticks_key(entry)]
    for instance in state_instances(entry):
        async_add_entities([_ZoneTick(scheduler, instance)], config_subentry_id=instance.subentry_id)


class _ZoneTick(EventEntity):
    _attr_has_entity_name = True
    _attr_name = "Tick"
    _attr_icon = "mdi:metronome"
    _attr_event_types = [EVENT_TYPE_TICK]
    _attr_should_poll = False

    def __init__(self, scheduler: TickScheduler, instance: StateInstance) -> None:
        self._scheduler = scheduler
        self._instance = instance
        self._attr_unique_id = f"{instance.subentry_id}_tick"
        self.entity_id = f"event.{instance.prefix}flare_tick"
        self._attr_device_info = instance.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._scheduler.register(self._instance.subentry_id, self._instance.title, self._tick)
        )

    @callback
    def _tick(self) -> None:
        self._trigger_event(EVENT_TYPE_TICK)
        self.async_write_ha_state()
