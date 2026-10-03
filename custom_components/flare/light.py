"""Flare lights: one per flare, on the Flares entry.

A flare is a light group whose members are its automation's lights, read
live. A bare turn-on runs the automation, so the room comes on however
the automation decides; a turn-on with values goes to the lights like any
light group's, which is an override. See flares/instance.py."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.automation import EVENT_AUTOMATION_RELOADED
from homeassistant.components.group.light import LightGroup
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.target import TargetStateChangedData, async_track_target_selector_state_change_event

from .const import (
    CONF_AREA,
    CONF_ENTRY_TYPE,
    CONF_TURN_OFF,
    DOMAIN,
    ENTRY_TYPE_FLARES,
    TURN_OFF_LIGHT,
)
from .flares.automation import automation_entity_id, automation_exists, lights_target, zone_device_id
from .flares.bare import is_bare_turn_on
from .flares.instance import FlareInstance, flare_instances

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_FLARES:
        return
    devices = dr.async_get(hass)
    for instance in flare_instances(entry):
        is_new = devices.async_get_device_by_identifier((DOMAIN, instance.subentry_id), entry.entry_id) is None
        async_add_entities([FlareLight(instance)], config_subentry_id=instance.subentry_id)
        if is_new:
            _place_in_area(hass, entry, instance)


def _place_in_area(hass: HomeAssistant, entry: ConfigEntry, instance: FlareInstance) -> None:
    """Puts a newly created flare's device in the area chosen when it was
    added. Only ever on creation: after that the area is the user's."""
    area_id = instance.config.get(CONF_AREA)
    if not area_id or ar.async_get(hass).async_get_area(area_id) is None:
        return
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier((DOMAIN, instance.subentry_id), entry.entry_id)
    if device is not None:
        devices.async_update_device(device.id, area_id=area_id)


def is_flare_light(hass: HomeAssistant, entity_id: str) -> bool:
    """True for a flare's own light, which must never be one of a room's lights."""
    entry = er.async_get(hass).async_get(entity_id)
    return entry is not None and entry.platform == DOMAIN and entry.domain == "light"


class FlareLight(LightGroup):
    """A light group over the flare's automation's lights."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = None

    def __init__(self, instance: FlareInstance) -> None:
        super().__init__(unique_id=f"{instance.subentry_id}_light", name=None, entity_ids=[], mode=None)
        self._attr_name = None
        self._instance = instance
        self._attr_device_info = instance.device_info
        self.entity_id = f"light.{instance.prefix}flare"
        self._untrack: CALLBACK_TYPE | None = None
        self._members_known = False

    async def async_added_to_hass(self) -> None:
        # Not GroupEntity's: its members are a fixed list, and these change
        # with the automation, the area and the registries.
        self.async_on_remove(self._stop_tracking)
        self.async_on_remove(self.hass.bus.async_listen(EVENT_AUTOMATION_RELOADED, self._async_retrack))
        self.async_on_remove(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_automation_registry_changed)
        )
        if not self.hass.is_running:
            # Automations load after this integration, so wait for them.
            self.async_on_remove(
                self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._async_retrack)
            )
        await self._async_track()

    @callback
    def _stop_tracking(self) -> None:
        if self._untrack is not None:
            self._untrack()
            self._untrack = None

    async def _async_retrack(self, _event: Event | None = None) -> None:
        await self._async_track()

    async def _async_automation_registry_changed(self, event: Event) -> None:
        """Retrack when the automation is renamed, removed or added."""
        if event.data.get("entity_id", "").startswith("automation.") or event.data.get(
            "old_entity_id", ""
        ).startswith("automation."):
            await self._async_track()

    async def _async_track(self) -> None:
        self._stop_tracking()
        entity_id = automation_entity_id(self.hass, self._instance.config)
        target = lights_target(self.hass, self._instance.config) if automation_exists(self.hass, entity_id) else None
        # With no lights the group reads as unavailable.
        if target is None:
            self._set_members(set())
            return
        self._members_known = False
        try:
            self._untrack = await async_track_target_selector_state_change_event(
                self.hass,
                target,
                self._members_changed_state,
                entity_filter=self._only_room_lights,
                on_entities_update=self._members_changed,
            )
        except Exception:  # noqa: BLE001 - an empty or broken target leaves the flare unavailable
            _LOGGER.debug("Flare %s has no lights to track", self.entity_id, exc_info=True)
            self._set_members(set())
            return
        if not self._members_known:
            # The tracker only reports a change, and an empty target is none.
            self._set_members(set())

    @callback
    def _only_room_lights(self, entity_ids: set[str]) -> set[str]:
        return {e for e in entity_ids if e.startswith("light.") and not is_flare_light(self.hass, e)}

    @callback
    def _members_changed(self, added, removed, states) -> None:
        self._members_known = True
        self._set_members(set(states))

    @callback
    def _set_members(self, entity_ids: set[str]) -> None:
        self._entity_ids = sorted(entity_ids)
        self._attr_extra_state_attributes = {ATTR_ENTITY_ID: self._entity_ids}
        for entity_id in self._entity_ids:
            self.async_update_supported_features(entity_id, self.hass.states.get(entity_id))
        self.async_update_group_state()
        self.async_write_ha_state()

    @callback
    def _members_changed_state(self, data: TargetStateChangedData) -> None:
        self.async_set_context(data.state_change_event.context)
        self.async_update_group_state()
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Bare: run the automation, which decides how the room comes on.
        With values: send them to every light, as a light group does."""
        if not is_bare_turn_on(kwargs):
            await super().async_turn_on(**kwargs)
            return
        await self.hass.services.async_call(
            "automation",
            "trigger",
            {ATTR_ENTITY_ID: automation_entity_id(self.hass, self._instance.config)},
            blocking=True,
            context=self._context,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._instance.config.get(CONF_TURN_OFF) == TURN_OFF_LIGHT or not self.hass.services.has_service(
            DOMAIN, "turn_off"
        ):
            # flare.turn_off belongs to the Zones entry, which may not be loaded.
            await super().async_turn_off(**kwargs)
            return
        # flare.turn_off records an off claim, so the room's own turn-on
        # paths don't read these lights as switched off by someone else.
        data: dict[str, Any] = {
            "entities": self._entity_ids,
            "zone_device_id": zone_device_id(self.hass, self._instance.config),
        }
        if "transition" in kwargs:
            data["transition"] = kwargs["transition"]
        await self.hass.services.async_call(DOMAIN, "turn_off", data, blocking=True, context=self._context)
