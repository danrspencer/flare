"""Claims survive a restart, via the tracking entity's restore state. The
entity is added through a real EntityPlatform, since RestoreEntity only
saves and restores for an entity that's genuinely added."""

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
)

from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_TRACKING, SUBENTRY_TYPE_STATE
from custom_components.flare.tracking.scope import state_instances
from custom_components.flare.sensor import _classify_tracked
from custom_components.flare.sensor import async_setup_entry as sensor_setup
from custom_components.flare.tracking.write_tracking import ClaimRegistry

ASKED = {"brightness": 200, "color_temp_kelvin": 3000}


def _claim(context_id: str, *, age: timedelta = timedelta(0)) -> dict:
    """A landed write: both claims carry the target."""
    seen = (dt_util.utcnow() - age).isoformat()

    def one(ctx):
        return {"context_id": ctx, "secondary_context_id": None, "recorded_at": seen, "target": ASKED}

    return {"observed": one(f"{context_id}-before"), "latest": one(context_id), "last_seen": seen}


async def _start(hass: HomeAssistant, restored_claims: dict | None = None):
    """One scope, its tracking entity added for real, with claims in the
    restore cache if given."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_TRACKING},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_STATE,
                title="Kitchen",
                unique_id="kitchen",
                data={},
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
    # A fresh context, as after a restart: only values can match.
    hass.states.async_set(entity_id, state, attrs, context=Context())


def _status(hass: HomeAssistant, tracker, entity_id: str) -> str:
    return _classify_tracked(hass, entity_id, tracker.claims[entity_id])[0]


async def test_what_is_saved_is_the_claims_themselves(hass: HomeAssistant):
    """Through a real dump to storage, so through HA's JSON encoder too."""
    _, tracker = await _start(hass)
    claim = _claim("ctx-ours")
    tracker.claims["light.a"] = claim

    saved = await async_mock_restore_state_shutdown_restart(hass)

    assert saved.last_states[tracker.entity_id].extra_data.as_dict() == {"claims": {"light.a": claim}}


async def test_claims_come_back_after_a_restart(hass: HomeAssistant):
    registry, _ = await _start(hass, {"light.a": _claim("ctx-ours")})

    assert set(registry.all_records()) == {"light.a"}


async def test_a_light_someone_else_had_before_the_restart_is_still_theirs(hass: HomeAssistant):
    """We asked for 200; it shows 90, so it's somebody else's."""
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)

    _, tracker = await _start(hass, {"light.a": _claim("ctx-ours")})

    assert _status(hass, tracker, "light.a") == "overridden"


async def test_a_light_unchanged_across_the_restart_is_still_ours(hass: HomeAssistant):
    """Unchanged across the restart: ours, by value."""
    _light(hass, "light.a", "on", brightness=200, color_temp_kelvin=3000)

    _, tracker = await _start(hass, {"light.a": _claim("ctx-ours")})

    assert _status(hass, tracker, "light.a") == "controlled"


async def test_a_restored_claim_over_a_day_old_is_dropped(hass: HomeAssistant):
    """The setup-time prune ran before the entity existed. The fresh claim
    beside it rules out "nothing was restored"."""
    registry, _ = await _start(
        hass, {"light.fresh": _claim("ctx-1"), "light.stale": _claim("ctx-2", age=timedelta(days=2))}
    )

    assert set(registry.all_records()) == {"light.fresh"}


async def test_reconnecting_after_a_restart_does_not_take_the_light_back(hass: HomeAssistant):
    """A reconnect (unavailable, unknown, on, as MQTT lights do) must not
    re-baseline the light as ours."""
    registry, tracker = await _start(hass, {"light.a": _claim("ctx-ours")})
    unsub = registry.async_start_listening(hass)

    _light(hass, "light.a", "unavailable")
    _light(hass, "light.a", "unknown")
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)
    await hass.async_block_till_done()

    assert _status(hass, tracker, "light.a") == "overridden"
    unsub()


async def test_a_light_reconnecting_as_off_does_not_release_its_siblings(hass: HomeAssistant):
    """The first light back being off, with siblings still unknown, must not
    release the scope's restored claims."""
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
