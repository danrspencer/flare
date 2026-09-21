"""
FLARE.

Sets up the integration: its two config entries (Schedules and Tracking),
their platforms, and the dashboard front-end files.

- The eight services - apply_lighting, turn_off, the compute_* planners
  and the claims_* override-protection calls - are registered by
  services.py, for the Tracking entry. They are plain Home Assistant
  services, usable from any automation.
- Day-phase/curve sensors, the phase-override select and the schedule/curve
  config entities (sensor.py, select.py, time.py, number.py, switch.py) are
  set up per named schedule, all sharing one ScheduleCoordinator
  (coordinator.py) - a native replacement for a Jinja packages/*.yaml
  setup. See config_flow.py for how they are added.
- Override protection's claims live on the Tracking entry's state devices
  (write_tracking.py, sensor.py).

Designed to work with the FLARE blueprint in this repo, but not coupled to
it: call any of the services directly from your own automations if that's
more useful to you. See README.md and services.yaml (visible in Developer
Tools -> Actions) for each service's contract on its own terms.

The decision logic - curve.py, grouping.py, scenes.py, two_step.py,
override_protection.py - is never handed a `hass`; services.py and the
platform modules are the places that read real Home Assistant state and
hand it over. (curve.py and override_protection.py each import one colour
helper from homeassistant.util.color, so "takes no `hass` object" is the
accurate description, not "has no Home Assistant dependency".)
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.loader import async_get_integration
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

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
from .config_flow import _areas_with_lights
from .coordinator import ScheduleCoordinator, schedule_instances
from .services import async_setup_services, async_unload_services
from .write_tracking import PRUNE_CHECK_INTERVAL, ClaimRegistry

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
# builds a settings view, one section per schedule sensor. Shipping it
# here rather than having people paste generated YAML is what lets a
# layout change reach existing installs through a HACS update.
# flare-section.js holds the layout both it and anything else would use,
# and is pulled in by the strategy's own import rather than a third
# add_extra_js_url - it registers nothing, so loading it on every page
# would be pure cost.
STRATEGY_JS_PATH = "flare-view-strategy.js"
BRIGHTNESS_JS_PATH = "flare-brightness-feature.js"
# flare-value-slider.js is deliberately absent: it registers nothing on
# its own, and the two features import it, so loading it separately on
# every page would be pure cost.


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve www/flare-curve-card.js and auto-load it on
    every frontend page - runs once for the whole domain, regardless of
    how many config entries/subentries exist, so the cards ship and
    update with the integration itself (via HACS) rather than needing
    a separate manual Lovelace resource registration step that can
    silently drift out of sync with them (see CLAUDE.md for the live
    incident this replaced). One static path serves the whole www/
    directory, so a second card would need only a second
    add_extra_js_url call, not a second StaticPathConfig.

    THE URL CARRIES THE VERSION, which is what makes the caching correct.
    It was previously an unversioned path with cache_headers=False, on
    the reasoning that not caching beat serving something stale. That
    reasoning was wrong: cache_headers=False does not disable caching, it
    only omits Cache-Control - the response still carries ETag and
    Last-Modified, and a response with no explicit freshness may be
    cached HEURISTICALLY, commonly a fraction of its own age. Safari does
    so keenly, and a just-deployed card and feature both rendered as
    "Configuration error" until that window lapsed.

    With the version in the path, every release is a new URL, so a cached
    copy can never be taken for the current one - and cache_headers goes
    back to True, since immutable content at an immutable URL is better
    than revalidating on every load.

    It has to be a path segment rather than a `?v=` query: these modules
    import each other relatively, and a relative import resolves against
    the importing module's own URL. A path is inherited by those imports;
    a query is not, so the card would load twice under two URLs and the
    second customElements.define would throw."""
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v2 -> v3: split the single entry into schedules and tracking.

    Both kinds of thing used to live under one entry as sibling
    subentries, which HA's integration page renders as one section each
    - so a house with a scope per room got a wall of peers with no
    grouping. An entry is the only level at which the distinction can be
    expressed (see const.py's CONF_ENTRY_TYPE).

    The existing entry becomes the **schedules** one, keeping its sensor
    subentries and, with them, every schedule time and curve value the
    user has set - those are real configuration and are worth preserving.
    Its state subentries are dropped and the tracking entry re-seeds
    equivalents from the same areas: a scope carries only a target, and
    claims aren't persisted at all, so there is nothing there to lose.

    (v1 -> v2 seeded state devices onto the single entry. That still runs
    first for anyone upgrading from v1, and this step then moves them;
    running it is harmless either way, since the seeding is idempotent
    per area and the subentries are about to be replaced.)"""
    if entry.version >= 3:
        return True

    if entry.version < 2:
        for area_id, name in _areas_with_lights(hass):
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType({CONF_TARGET: {"area_id": [area_id]}}),
                    subentry_type=SUBENTRY_TYPE_STATE,
                    title=name,
                    unique_id=slugify(name),
                ),
            )

    for subentry in list(entry.subentries.values()):
        if subentry.subentry_type == SUBENTRY_TYPE_STATE:
            hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)

    hass.config_entries.async_update_entry(
        entry,
        version=3,
        title="FLARE Schedules",
        unique_id=f"{DOMAIN}_{ENTRY_TYPE_SCHEDULES}",
        data={**entry.data, CONF_ENTRY_TYPE: ENTRY_TYPE_SCHEDULES},
    )
    # Created as its own entry rather than here, so it goes through the
    # same flow a fresh install uses and can't drift from it.
    hass.async_create_task(
        hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={})
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    is_tracking = entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TRACKING

    # Shared across every apply_lighting call, from whichever automation
    # made it - see write_tracking.py for why (grouping.py's
    # externally_set() check only cares "did adaptive control write this
    # most recently", not which specific caller). The claims themselves
    # live on the state devices' tracking entities and are restored with
    # them across a restart - see write_tracking.py's module docstring.
    write_tracker = ClaimRegistry(hass, entry)
    # An entity deleted from HA outright (not just restarting - e.g. a
    # Zigbee2MQTT group removed at the source) never triggers the
    # unavailable-transition cleanup async_start_listening watches for,
    # since hass.states.get(...) just returns None forever with nothing
    # left to observe - see async_prune_stale's own docstring for the
    # live incident (light.extension_spots_left) that prompted this.
    # Called once here (catches anything that went stale while HA was
    # down) and again every PRUNE_CHECK_INTERVAL below (keeps the
    # promise current while running, not just at the next restart).
    if is_tracking:
        await write_tracker.async_prune_stale()

        async def _periodic_prune(now) -> None:
            await write_tracker.async_prune_stale()

        entry.async_on_unload(
            async_track_time_interval(hass, _periodic_prune, PRUNE_CHECK_INTERVAL, cancel_on_shutdown=True)
        )
        entry.async_on_unload(write_tracker.async_start_listening(hass))

    # Raises a fixable repair when the installed blueprint is older than
    # the one this release ships with - the two halves deploy separately
    # and nothing else tells you they have drifted (see
    # blueprint_check.py).
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


    # Reloads the entry on any entry/subentry change - covers the main
    # entry's reconfigure flow, and (since adding/removing/reconfiguring a
    # subentry doesn't otherwise trigger a reload on its own) named
    # sensors added via the "Add Sensor" subentry flow too. config_flow.py
    # deliberately uses async_update_and_abort rather than
    # *_reload_and_abort so this is the only thing that reloads - the
    # subentry version of *_reload_and_abort raises if an update listener
    # is registered, and duplicating it here would double-reload anyway.

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if is_tracking:
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = write_tracker
        _async_remove_legacy_owner_devices(hass, entry)
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
            # @callback marks this as event-loop-safe for HA's job
            # dispatcher - without it, a plain function here gets run in
            # the executor thread pool instead (HassJobType.Executor),
            # and hass.async_create_task() is only safe to call from the
            # event loop itself. Confirmed against HA core source
            # (get_hassjob_callable_job_type) after this fired a real
            # "calls hass.async_create_task from a thread other than the
            # event loop" RuntimeError in production - undecorated sync
            # listeners are silently unsafe here, not just a lint nit.
            for instance in instances:
                hass.async_create_task(hass.data[DOMAIN][instance.subentry_id].async_request_refresh())

        # Evening tracks sun.sun, so a sunset update should take effect
        # without waiting for the next 60s poll. This is the only entity
        # tracked here: the schedule/curve config entities and the
        # phase-override select each refresh their own coordinator
        # themselves on change (see time.py/number.py/select.py) - each
        # is the only writer of its own state, so routing their changes
        # back through the state machine here would just be a second,
        # global copy of a refresh the entity already owns.
        entry.async_on_unload(async_track_state_change_event(hass, ["sun.sun"], _refresh_all))

    # Unconditional, not gated on instances - the write-tracking sensor
    # (sensor.py) is entry-scoped and should exist even with zero
    # schedule instances configured. Harmless when instances is empty:
    # each platform's own async_setup_entry loop over schedule_instances()
    # just adds nothing for the per-instance entities.
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


def _owner_devices(hass: HomeAssistant, entry: ConfigEntry) -> list[dr.DeviceEntry]:
    """Every per-owner device on this entry - i.e. everything except the
    schedule-instance devices (coordinator.py's ScheduleInstance.
    device_info), which are keyed on a subentry_id instead."""
    return [
        device
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if any(domain == DOMAIN and key.startswith("owner_") for domain, key in device.identifiers)
    ]


@callback
def _async_remove_legacy_owner_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Removes the devices from when tracking scopes were derived from
    the calling automation's entity_id rather than configured.

    Those were created on the fly from a caller-supplied string, which
    is exactly the "devices appearing by magic" this replaced. Nothing
    is lost by deleting them: claims are no longer persisted at all, so
    there is no state in them to preserve, and removing a device takes
    its entities with it."""
    registry = dr.async_get(hass)
    for device in _owner_devices(hass, entry):
        registry.async_remove_device(device.id)
