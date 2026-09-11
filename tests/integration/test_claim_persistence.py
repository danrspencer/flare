"""
Claims survive a restart.

The claims live on each state device's tracking entity, which is a
RestoreEntity, so they ride Home Assistant's own restore state. These
cover both halves - what is saved, and what comes back - plus the two
rules in write_tracking.py's state_changed listener that would otherwise
undo a restore within seconds of it happening.

Unlike test_services.py and test_state_devices.py, which attach the
tracking entity with a capturing async_add_entities, these add it through
a real EntityPlatform: RestoreEntity only saves or restores for an entity
that has genuinely been added to Home Assistant.
"""

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers import area_registry as ar
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
)

from custom_components.flare.const import CONF_ENTRY_TYPE, CONF_TARGET, DOMAIN, ENTRY_TYPE_TRACKING, SUBENTRY_TYPE_STATE
from custom_components.flare.coordinator import state_instances
from custom_components.flare.sensor import _classify_tracked
from custom_components.flare.sensor import async_setup_entry as sensor_setup
from custom_components.flare.write_tracking import ClaimRegistry

ASKED = {"brightness": 200, "color_temp_kelvin": 3000}


def _claim(context_id: str, *, age: timedelta = timedelta(0)) -> dict:
    """A claim for a write that landed: `observed` and `latest` both carry
    the target, the ordinary shape once any write has been confirmed."""
    seen = (dt_util.utcnow() - age).isoformat()

    def one(ctx):
        return {"context_id": ctx, "secondary_context_id": None, "recorded_at": seen, "target": ASKED}

    return {"observed": one(f"{context_id}-before"), "latest": one(context_id), "last_seen": seen}


async def _start(hass: HomeAssistant, restored_claims: dict | None = None):
    """One tracking scope whose tracking entity is added through a real
    platform - with claims waiting in the restore cache, if given, the way
    they would be on the far side of a restart."""
    area = ar.async_get(hass).async_get_or_create("Kitchen")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_STATE,
                title="Kitchen",
                unique_id="kitchen",
                data={CONF_TARGET: {"area_id": [area.id]}},
            )
        ],
    )
    entry.add_to_hass(hass)
    registry = ClaimRegistry(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = registry

    added: list = []
    await sensor_setup(hass, entry, lambda entities, **kw: added.extend(entities))
    tracker = next(e for e in added if hasattr(e, "claims"))
    if restored_claims is not None:
        mock_restore_cache_with_extra_data(
            hass, [(State(tracker.entity_id, str(len(restored_claims))), {"claims": restored_claims})]
        )

    platform = MockEntityPlatform(hass, domain="sensor", platform_name=DOMAIN)
    platform.config_entry = entry
    await platform.async_add_entities([tracker], config_subentry_id=state_instances(entry)[0].subentry_id)
    await hass.async_block_till_done()
    return registry, tracker


def _light(hass: HomeAssistant, entity_id: str, state: str, **attrs) -> None:
    # A fresh Context every time, as every light reporting in after a
    # restart gets - which is why no restored claim can match on context,
    # and everything here rests on the value comparison.
    hass.states.async_set(entity_id, state, attrs, context=Context())


def _status(hass: HomeAssistant, tracker, entity_id: str) -> str:
    return _classify_tracked(hass, entity_id, tracker.claims[entity_id])[0]


async def test_what_is_saved_is_the_claims_themselves(hass: HomeAssistant):
    """The save half, through a real dump to storage and back - which is
    also what proves a claim survives HA's JSON encoder intact."""
    _, tracker = await _start(hass)
    claim = _claim("ctx-ours")
    tracker.claims["light.a"] = claim

    saved = await async_mock_restore_state_shutdown_restart(hass)

    assert saved.last_states[tracker.entity_id].extra_data.as_dict() == {"claims": {"light.a": claim}}


async def test_claims_come_back_after_a_restart(hass: HomeAssistant):
    registry, _ = await _start(hass, {"light.a": _claim("ctx-ours")})

    assert set(registry.all_records()) == {"light.a"}


async def test_a_light_someone_else_had_before_the_restart_is_still_theirs(hass: HomeAssistant):
    """The whole point. FLARE last asked for 200; the lamp is showing 90,
    so somebody else set it, and a restart is no reason to take it back."""
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)

    _, tracker = await _start(hass, {"light.a": _claim("ctx-ours")})

    assert _status(hass, tracker, "light.a") == "overridden"


async def test_a_light_unchanged_across_the_restart_is_still_ours(hass: HomeAssistant):
    """The other half, and the reason persistence is safe now: the fresh
    context can't match, but the value still does. The first persisted
    version had no value fallback, and read every one of these as
    overridden - 57 lights excluded after every restart (#69)."""
    _light(hass, "light.a", "on", brightness=200, color_temp_kelvin=3000)

    _, tracker = await _start(hass, {"light.a": _claim("ctx-ours")})

    assert _status(hass, tracker, "light.a") == "controlled"


async def test_a_restored_claim_over_a_day_old_is_dropped(hass: HomeAssistant):
    """The setup-time prune runs before any tracking entity exists, so the
    restore has to prune for itself. One fresh claim beside the stale one,
    or "nothing was restored at all" would pass this too."""
    registry, _ = await _start(
        hass, {"light.fresh": _claim("ctx-1"), "light.stale": _claim("ctx-2", age=timedelta(days=2))}
    )

    assert set(registry.all_records()) == {"light.fresh"}


async def test_reconnecting_after_a_restart_does_not_take_the_light_back(hass: HomeAssistant):
    """The listener used to re-baseline any light arriving in a real state
    from unavailable/unknown, making whatever it showed "ours". It only
    ever fired on restarts - a genuine dropout has its claim cleared first
    - so with claims restored it would hand every override back moments
    later. The sequence is the one a real MQTT light went through on the
    live instance: unavailable, then its own unknown, then on."""
    registry, tracker = await _start(hass, {"light.a": _claim("ctx-ours")})
    unsub = registry.async_start_listening(hass)

    _light(hass, "light.a", "unavailable")
    _light(hass, "light.a", "unknown")
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)
    await hass.async_block_till_done()

    assert _status(hass, tracker, "light.a") == "overridden"
    unsub()


async def test_a_light_reconnecting_as_off_does_not_release_its_siblings(hass: HomeAssistant):
    """A scope releases every claim once none of its lights are on. After
    a restart lights reconnect one at a time, so if the first one back
    happens to be off, its siblings are still `unknown` - which counts as
    dark. Releasing then would throw their restored overrides away. Only a
    real on/off -> off is somebody switching a light off."""
    registry, _ = await _start(hass, {"light.a": _claim("ctx-a"), "light.b": _claim("ctx-b")})
    unsub = registry.async_start_listening(hass)

    _light(hass, "light.a", "unavailable")
    _light(hass, "light.a", "unknown")
    _light(hass, "light.b", "unavailable")
    _light(hass, "light.b", "unknown")
    _light(hass, "light.b", "off")
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.a", "light.b"}
    unsub()
