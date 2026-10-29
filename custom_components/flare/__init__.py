"""FLARE: sets up the Schedules, Settings and Flares config entries, their
platforms, and the dashboard front-end files. Code layout and the
dependency rule are in CONTRIBUTING.md."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
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
    ENTRY_TYPE_FLARES,
    ENTRY_TYPE_SETTINGS,
    EVENT_TYPE_TICK,
    SETTINGS_ENTRY_TITLE,
    SUBENTRY_TYPE_ZONE,
)
from homeassistant.helpers.start import async_at_started

from .blueprint_check import async_check as async_check_blueprint
from .dashboard_reload import FrontendLoadedView, OldFingerprintView
from .schedule.coordinator import ScheduleCoordinator, schedule_instances
from .services.handlers import async_setup_services, async_unload_services
from .services.schedules import async_setup_schedule_services
from .services.targets import async_setup_target_services
from .flares.instance import flare_instances
from .tracking.ticker import TickScheduler
from .tracking.claims import PRUNE_CHECK_INTERVAL, ClaimRegistry

# Both entry types use the sensor platform; each platform module checks
# the entry type to decide what it adds.
SCHEDULE_PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER, Platform.TIME, Platform.SWITCH, Platform.EVENT]
SETTINGS_PLATFORMS = [Platform.SENSOR, Platform.BUTTON]
FLARE_PLATFORMS = [Platform.LIGHT]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL_BASE = "/flare_static"
# Loads the modules that register something, once HA's frontend is ready
# for them; those import the rest.
LOADER_JS_PATH = "flare-loader.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve www/, load the front-end modules on every page, and register
    the schedule and target services, which belong to neither entry.

    The URL carries a fingerprint of the files and is cached hard, so any
    change to them is a new URL; an old one redirects to it. A path
    segment, not `?v=`: the modules import each other relatively, and a
    query isn't inherited by relative imports."""
    www = Path(__file__).parent / "www"
    base = f"{CARD_URL_BASE}/{await hass.async_add_executor_job(www_fingerprint, www)}"
    await hass.http.async_register_static_paths([StaticPathConfig(base, str(www), cache_headers=True)])
    add_extra_js_url(hass, f"{base}/{LOADER_JS_PATH}")
    hass.http.register_view(OldFingerprintView(base))
    hass.http.register_view(FrontendLoadedView())
    async_setup_schedule_services(hass)
    async_setup_target_services(hass)
    return True


def www_fingerprint(directory: Path) -> str:
    """A short hash of every file's name and contents."""
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Minor version 1 -> 2 is 2.0: the zones go, with their devices and
    claims, and the Zones entry, still titled by its old default, becomes
    Settings."""
    if entry.version != 3:
        return False
    if entry.minor_version < 2:
        if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SETTINGS:
            for subentry_id, subentry in list(entry.subentries.items()):
                if subentry.subentry_type == SUBENTRY_TYPE_ZONE:
                    hass.config_entries.async_remove_subentry(entry, subentry_id)
            if entry.title == "Zones":
                hass.config_entries.async_update_entry(entry, title=SETTINGS_ENTRY_TITLE)
        hass.config_entries.async_update_entry(entry, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES:
        entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
        # Only with flares, so an empty entry doesn't load the light platform.
        # runtime_data says whether it did, for the unload.
        entry.runtime_data = bool(flare_instances(entry))
        if entry.runtime_data:
            await hass.config_entries.async_forward_entry_setups(entry, FLARE_PLATFORMS)
        return True

    # Subentry changes don't reload on their own. This is the only reload,
    # which is why config_flow.py uses async_update_and_abort.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SETTINGS:
        await _async_setup_settings(hass, entry)
        return True

    # Each schedule's coordinator, by subentry id.
    entry.runtime_data = coordinators = {}
    instances = schedule_instances(entry)
    if instances:
        for instance in instances:
            coordinator = ScheduleCoordinator(hass, instance)
            await coordinator.async_config_entry_first_refresh()
            coordinators[instance.subentry_id] = coordinator

        @callback
        def _refresh_all(event) -> None:
            # Must stay @callback: otherwise it runs in the executor, where
            # async_create_task raises.
            for coordinator in coordinators.values():
                hass.async_create_task(coordinator.async_request_refresh())

        # Evening tracks sunset. Config entities refresh their own coordinator.
        entry.async_on_unload(async_track_state_change_event(hass, ["sun.sun"], _refresh_all))

    await hass.config_entries.async_forward_entry_setups(entry, SCHEDULE_PLATFORMS)

    if instances:
        # The first refresh ran before the config entities existed, so it
        # used defaults. Recompute now they've restored their values.
        for coordinator in coordinators.values():
            await coordinator.async_refresh()

    return True


async def _async_setup_settings(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The claims, the services and the area ticks."""
    registry = ClaimRegistry(hass)
    await registry.async_load()
    entry.runtime_data = registry

    # Pruning catches entities deleted outright, which the listener never
    # sees go unavailable.
    @callback
    def _periodic_prune(now) -> None:
        registry.async_prune_stale()

    entry.async_on_unload(
        async_track_time_interval(hass, _periodic_prune, PRUNE_CHECK_INTERVAL, cancel_on_shutdown=True)
    )
    entry.async_on_unload(registry.async_start_listening(hass))

    # After startup, since automations (which decide whether a blueprint
    # is in use) may not have loaded yet during setup.
    async def _check_blueprint(_event=None) -> None:
        await async_check_blueprint(hass)

    entry.async_on_unload(async_at_started(hass, _check_blueprint))
    async_setup_services(hass, entry, registry)

    scheduler = TickScheduler(
        hass,
        int(entry.options.get(CONF_TICK_INTERVAL, DEFAULT_TICK_INTERVAL)),
        float(entry.options.get(CONF_TICK_GAP, DEFAULT_TICK_GAP)),
    )
    entry.async_on_unload(scheduler.stop)

    @callback
    def _stop_ticking(_event: Event) -> None:
        scheduler.stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_ticking))
    await hass.config_entries.async_forward_entry_setups(entry, SETTINGS_PLATFORMS)
    # Once the claim events are listening, so these are announced: rooms whose
    # lights went dark while HA wasn't watching won't change again to be
    # released, and claims from long ago are stale.
    registry.release_settled_dark_rooms()
    registry.async_prune_stale()
    entry.async_on_unload(_tick_areas(hass, scheduler))


def _tick_areas(hass: HomeAssistant, scheduler: TickScheduler) -> Callable[[], None]:
    """Ticks every area, kept in step with the area registry. Each tick is a
    plain event naming the area, so it never shows in Activity, history or
    the logbook. Returns the cleanup."""

    def _fire(area_id: str) -> Callable[[], None]:
        @callback
        def _tick() -> None:
            hass.bus.async_fire(EVENT_TYPE_TICK, {"area_id": area_id})

        return _tick

    @callback
    def _sync(_event: Event | None = None) -> None:
        scheduler.set_areas({area.id: (area.name, _fire(area.id)) for area in ar.async_get(hass).async_list_areas()})

    _sync()
    return hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, _sync)


_RELOADS_QUEUED = "reloads_queued"


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """One reload for changes made together, such as adding several flares at
    once: the first listener yields so the rest see it queued, then clears the
    mark before reloading, so a later change still gets its own reload."""
    queued = hass.data.setdefault(DOMAIN, {}).setdefault(_RELOADS_QUEUED, set())
    if entry.entry_id in queued:
        return
    queued.add(entry.entry_id)
    await asyncio.sleep(0)
    queued.discard(entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_FLARES:
        if not entry.runtime_data:
            return True
        return await hass.config_entries.async_unload_platforms(entry, FLARE_PLATFORMS)

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SETTINGS:
        async_unload_services(hass)
        return await hass.config_entries.async_unload_platforms(entry, SETTINGS_PLATFORMS)

    return await hass.config_entries.async_unload_platforms(entry, SCHEDULE_PLATFORMS)
