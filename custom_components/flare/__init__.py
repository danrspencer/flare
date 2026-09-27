"""
FLARE.

Sets up the integration: its two config entries (Schedules and Tracking),
their platforms, and the dashboard front-end files.

- The eight services - apply_lighting, turn_off, the compute_* planners
  and the claims_* override-protection calls - are registered by
  services/handlers.py, for the Tracking entry. They are plain Home
  Assistant services, usable from any automation.
- The code is grouped by concept - schedule/, tracking/, services/ - see
  CONTRIBUTING.md for why and for the dependency rule.
- Day-phase/curve sensors, the phase-override select and the schedule/curve
  config entities (sensor.py, select.py, time.py, number.py, switch.py) are
  set up per named schedule, each with its own ScheduleCoordinator
  (coordinator.py). See config_flow.py for how they are added.
- Override protection's claims live on the Tracking entry's state devices
  (write_tracking.py, sensor.py).

Designed to work with the FLARE blueprint in this repo, but not coupled to
it: call any of the services directly from your own automations if that's
more useful to you. See README.md and services.yaml (visible in Developer
Tools -> Actions) for each service's contract on its own terms.

The decision logic - curve.py, grouping.py, scenes.py, two_step.py,
override_protection.py - is never handed a `hass`; services/handlers.py and the
platform modules are the places that read real Home Assistant state and
hand it over. (curve.py and override_protection.py each import one colour
helper from homeassistant.util.color, so "takes no `hass` object" is the
accurate description, not "has no Home Assistant dependency".)
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.loader import async_get_integration
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_ENTRY_TYPE,
    CONF_TARGET,
    DOMAIN,
    ENTRY_TYPE_SCHEDULES,
    ENTRY_TYPE_TRACKING,
    SUBENTRY_TYPE_STATE,
)
from homeassistant.helpers.start import async_at_started

from .blueprint_check import async_check as async_check_blueprint
from .schedule.coordinator import ScheduleCoordinator, schedule_instances
from .services.handlers import async_setup_services, async_unload_services
from .tracking.write_tracking import PRUNE_CHECK_INTERVAL, ClaimRegistry

# One list per entry type - see const.py's CONF_ENTRY_TYPE for why this
# integration installs as two entries rather than one. Both use the
# sensor platform; each platform module decides which entities it owns
# by checking the entry's type.
SCHEDULE_PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER, Platform.TIME, Platform.SWITCH]
TRACKING_PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


CARD_URL_BASE = "/flare_static"
CARD_JS_PATH = "flare-curve-card.js"
# A custom card feature, not a card - it renders a Kelvin-valued `number`
# as a slider whose track is the colour temperature it sets. Separate
# file because it is separately useful (a tile anywhere can use it), and
# it imports kelvinToRgb from the card above, so the two agree on colour
# by construction rather than by a second copy of the conversion.
FEATURE_JS_PATH = "flare-kelvin-feature.js"
# A Lovelace view strategy: `views: - strategy: {type: custom:flare-schedule}`
# builds a settings view, one section per schedule sensor, regenerated on
# every load so a layout change reaches existing dashboards with an update.
# flare-section.js holds the layout and is pulled in by the strategy's own
# import: it registers nothing, so loading it on every page would be waste.
STRATEGY_JS_PATH = "flare-view-strategy.js"
BRIGHTNESS_JS_PATH = "flare-brightness-feature.js"
# flare-value-slider.js is deliberately absent: it registers nothing on
# its own, and the two features import it, so loading it separately on
# every page would be pure cost.


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve www/ and auto-load the front-end modules on every page, so
    the cards ship and update with the integration rather than needing a
    Lovelace resource registered by hand. Runs once for the domain.

    The URL carries the integration version and is cached hard: every
    release is a new URL, so a cached copy can never be taken for the
    current one. Note that cache_headers=False would NOT prevent caching -
    it only omits Cache-Control, leaving ETag/Last-Modified, and browsers
    (Safari especially) then cache heuristically.

    The version is a path segment rather than a `?v=` query because these
    modules import each other relatively, and a relative import resolves
    against the importing module's URL. A path is inherited by those
    imports; a query is not, so the card would load twice under two URLs
    and the second customElements.define would throw."""
    integration = await async_get_integration(hass, DOMAIN)
    # Falls back only if the manifest has no version, which a HACS
    # install always does - still better than failing setup outright.
    base = f"{CARD_URL_BASE}/{integration.version or 'dev'}"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(base, str(Path(__file__).parent / "www"), cache_headers=True)]
    )
    for js in (CARD_JS_PATH, FEATURE_JS_PATH, BRIGHTNESS_JS_PATH, STRATEGY_JS_PATH):
        add_extra_js_url(hass, f"{base}/{js}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    is_tracking = entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TRACKING

    # Shared across every service call, from whichever automation made
    # it. The claims themselves live on the state devices' tracking
    # entities - see write_tracking.py's module docstring.
    write_tracker = ClaimRegistry(hass, entry)
    # An entity deleted from HA outright never goes through the
    # unavailable transition async_start_listening watches for, so its
    # claim would linger forever. Pruned once at setup (for anything
    # removed while HA was down) and then every PRUNE_CHECK_INTERVAL.
    if is_tracking:
        await write_tracker.async_prune_stale()

        async def _periodic_prune(now) -> None:
            await write_tracker.async_prune_stale()

        entry.async_on_unload(
            async_track_time_interval(hass, _periodic_prune, PRUNE_CHECK_INTERVAL, cancel_on_shutdown=True)
        )
        entry.async_on_unload(write_tracker.async_start_listening(hass))

    # Raises a fixable repair when the installed blueprint is missing or
    # older than this release's (see blueprint_check.py).
    #
    # Deferred to "started" rather than run here: automations are what
    # decide whether a blueprint is in use at all, and during setup they
    # may not have loaded yet, so checking now would find every
    # blueprint orphaned and report nothing. Tracking only, so a house
    # with both entries doesn't run it twice.
    if is_tracking:
        async def _check_blueprint(_event=None) -> None:
            await async_check_blueprint(hass)

        entry.async_on_unload(async_at_started(hass, _check_blueprint))

    # The services belong to the tracking entry: every one of them is
    # about which lights are being driven and by whom, and they need the
    # claim registry this entry owns.
    if is_tracking:
        async_setup_services(hass, entry, write_tracker)

    # Reloads the entry on any entry/subentry change, including adding,
    # removing or reconfiguring a subentry, which doesn't reload on its
    # own. config_flow.py uses async_update_and_abort rather than
    # *_reload_and_abort so this is the only reload: the subentry
    # *_reload_and_abort raises when an update listener is registered.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if is_tracking:
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = write_tracker
        await hass.config_entries.async_forward_entry_setups(entry, TRACKING_PLATFORMS)
        return True

    instances = schedule_instances(entry)
    if instances:
        for instance in instances:
            coordinator = ScheduleCoordinator(hass, instance)
            await coordinator.async_config_entry_first_refresh()
            hass.data.setdefault(DOMAIN, {})[instance.subentry_id] = coordinator

        @callback
        def _refresh_all(event) -> None:
            # Must stay @callback: an undecorated sync listener runs in the
            # executor (get_hassjob_callable_job_type), where
            # hass.async_create_task() raises a thread-safety RuntimeError.
            for instance in instances:
                hass.async_create_task(hass.data[DOMAIN][instance.subentry_id].async_request_refresh())

        # Evening tracks sun.sun, so a sunset update should take effect
        # without waiting for the next 60s poll. This is the only entity
        # tracked here: the schedule/curve config entities and the
        # phase-override select refresh their own coordinator on change
        # (see time.py/number.py/select.py).
        entry.async_on_unload(async_track_state_change_event(hass, ["sun.sun"], _refresh_all))

    # Unconditional, so unload always has platforms to unload: with no
    # schedules each platform simply adds nothing.
    await hass.config_entries.async_forward_entry_setups(entry, SCHEDULE_PLATFORMS)

    if instances:
        # The first refresh above ran before the time.*/number.* entities
        # existed (or while a reload had left them "unavailable"), so it
        # computed from defaults - see coordinator._time_ts(). Now that
        # the platforms are loaded and every config entity has restored
        # its real value, recompute once so the sensors reflect the
        # user's actual schedule immediately instead of up to 60s later.
        for instance in instances:
            await hass.data[DOMAIN][instance.subentry_id].async_refresh()

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TRACKING:
        async_unload_services(hass)
        unloaded = await hass.config_entries.async_unload_platforms(entry, TRACKING_PLATFORMS)
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        return unloaded

    instances = schedule_instances(entry)
    unloaded = await hass.config_entries.async_unload_platforms(entry, SCHEDULE_PLATFORMS)
    for instance in instances:
        hass.data.get(DOMAIN, {}).pop(instance.subentry_id, None)
    return unloaded
