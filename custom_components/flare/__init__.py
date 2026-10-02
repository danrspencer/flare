"""FLARE: sets up the Schedules and Zones config entries, their
platforms, and the dashboard front-end files. Code layout and the
dependency rule are in CONTRIBUTING.md."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.loader import async_get_integration
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_ENTRY_TYPE,
    CONF_TICK_GAP,
    CONF_TICK_INTERVAL,
    DEFAULT_TICK_GAP,
    DEFAULT_TICK_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_ZONES,
)
from homeassistant.helpers.start import async_at_started

from .blueprint_check import async_check as async_check_blueprint
from .schedule.coordinator import ScheduleCoordinator, schedule_instances
from .services.handlers import async_setup_services, async_unload_services
from .services.schedules import async_setup_schedule_services
from .event import ticks_key
from .zone.ticker import TickScheduler
from .zone.claims import PRUNE_CHECK_INTERVAL, ClaimRegistry

# Both entry types use the sensor platform; each platform module checks
# the entry type to decide what it adds.
SCHEDULE_PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER, Platform.TIME, Platform.SWITCH, Platform.EVENT]
ZONE_PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.EVENT]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL_BASE = "/flare_static"
CARD_JS_PATH = "flare-curve-card.js"
FEATURE_JS_PATH = "flare-kelvin-feature.js"
STRATEGY_JS_PATH = "flare-view-strategy.js"
BRIGHTNESS_JS_PATH = "flare-brightness-feature.js"
TRANSFER_JS_PATH = "flare-schedule-transfer-card.js"
# flare-section.js and flare-value-slider.js register nothing; the modules
# above import them.


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve www/, load the front-end modules on every page, and register
    the schedule services, which belong to neither entry.

    The URL is versioned and cached hard, so each release is a new URL.
    The version is a path segment, not `?v=`: the modules import each
    other relatively, and a query isn't inherited by relative imports."""
    integration = await async_get_integration(hass, DOMAIN)
    base = f"{CARD_URL_BASE}/{integration.version or 'dev'}"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(base, str(Path(__file__).parent / "www"), cache_headers=True)]
    )
    for js in (CARD_JS_PATH, FEATURE_JS_PATH, BRIGHTNESS_JS_PATH, TRANSFER_JS_PATH, STRATEGY_JS_PATH):
        add_extra_js_url(hass, f"{base}/{js}")
    async_setup_schedule_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    is_zones = entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ZONES

    registry = ClaimRegistry(hass, entry)
    # Pruning catches entities deleted outright, which the listener never
    # sees go unavailable.
    if is_zones:
        await registry.async_prune_stale()

        async def _periodic_prune(now) -> None:
            await registry.async_prune_stale()

        entry.async_on_unload(
            async_track_time_interval(hass, _periodic_prune, PRUNE_CHECK_INTERVAL, cancel_on_shutdown=True)
        )
        entry.async_on_unload(registry.async_start_listening(hass))

    # After startup, since automations (which decide whether a blueprint
    # is in use) may not have loaded yet during setup.
    if is_zones:
        async def _check_blueprint(_event=None) -> None:
            await async_check_blueprint(hass)

        entry.async_on_unload(async_at_started(hass, _check_blueprint))

    if is_zones:
        async_setup_services(hass, entry, registry)

    # Subentry changes don't reload on their own. This is the only reload,
    # which is why config_flow.py uses async_update_and_abort.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if is_zones:
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = registry
        scheduler = TickScheduler(
            hass,
            int(entry.options.get(CONF_TICK_INTERVAL, DEFAULT_TICK_INTERVAL)),
            float(entry.options.get(CONF_TICK_GAP, DEFAULT_TICK_GAP)),
        )
        hass.data[DOMAIN][ticks_key(entry)] = scheduler
        entry.async_on_unload(scheduler.stop)
        await hass.config_entries.async_forward_entry_setups(entry, ZONE_PLATFORMS)
        return True

    instances = schedule_instances(entry)
    if instances:
        for instance in instances:
            coordinator = ScheduleCoordinator(hass, instance)
            await coordinator.async_config_entry_first_refresh()
            hass.data.setdefault(DOMAIN, {})[instance.subentry_id] = coordinator

        @callback
        def _refresh_all(event) -> None:
            # Must stay @callback: otherwise it runs in the executor, where
            # async_create_task raises.
            for instance in instances:
                hass.async_create_task(hass.data[DOMAIN][instance.subentry_id].async_request_refresh())

        # Evening tracks sunset. Config entities refresh their own coordinator.
        entry.async_on_unload(async_track_state_change_event(hass, ["sun.sun"], _refresh_all))

    await hass.config_entries.async_forward_entry_setups(entry, SCHEDULE_PLATFORMS)

    if instances:
        # The first refresh ran before the config entities existed, so it
        # used defaults. Recompute now they've restored their values.
        for instance in instances:
            await hass.data[DOMAIN][instance.subentry_id].async_refresh()

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ZONES:
        async_unload_services(hass)
        unloaded = await hass.config_entries.async_unload_platforms(entry, ZONE_PLATFORMS)
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        hass.data.get(DOMAIN, {}).pop(ticks_key(entry), None)
        return unloaded

    instances = schedule_instances(entry)
    unloaded = await hass.config_entries.async_unload_platforms(entry, SCHEDULE_PLATFORMS)
    for instance in instances:
        hass.data.get(DOMAIN, {}).pop(instance.subentry_id, None)
    return unloaded
