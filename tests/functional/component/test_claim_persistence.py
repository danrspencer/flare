"""Claims survive a restart, saved to HA's storage. Each test starts the
Settings entry the way HA does, over whatever storage held before."""

from datetime import timedelta
from typing import Any

import pytest
from freezegun import freeze_time

from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import Context, CoreState, HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.flare.const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SETTINGS
from custom_components.flare.sensor import _classify_tracked
from custom_components.flare.tracking.claims import SAVE_DELAY, STORAGE_KEY, STORAGE_VERSION, ClaimRegistry
from custom_components.flare.tracking.override_protection import MISMATCH_GRACE
from tests.support.claims import after_the_grace

ASKED = {"brightness": 200, "color_temp_kelvin": 3000}
ROOM = "automation.kitchen"


@pytest.fixture(autouse=True)
def _real_setup(stub_entry_setup):
    """The entry set up as HA does, platforms and all."""


def _claim(context_id: str, *, age: timedelta = timedelta(0)) -> dict:
    """A landed write: both claims carry the target."""
    seen = (dt_util.utcnow() - age).isoformat()

    def one(ctx):
        return {"context_id": ctx, "secondary_context_id": None, "recorded_at": seen, "target": ASKED}

    return {"observed": one(f"{context_id}-before"), "latest": one(context_id), "last_seen": seen}


def _room(*lights: str) -> dict:
    return {ROOM: {"lights": sorted(lights), "last_seen": dt_util.utcnow().isoformat()}}


async def _start(
    hass: HomeAssistant, hass_storage: dict[str, Any], claims: dict | None = None, rooms: dict | None = None
) -> ClaimRegistry:
    """The Settings entry set up over storage holding these claims, all in
    one room unless rooms are given too."""
    if claims is not None:
        hass_storage[STORAGE_KEY] = {
            "version": STORAGE_VERSION,
            "minor_version": 1,
            "key": STORAGE_KEY,
            "data": {"claims": claims, "rooms": rooms if rooms is not None else _room(*claims)},
        }
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SETTINGS}, version=3, minor_version=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _light(hass: HomeAssistant, entity_id: str, state: str, **attrs) -> None:
    # A fresh context, as after a restart: only values can match.
    hass.states.async_set(entity_id, state, attrs, context=Context())


def _status(hass: HomeAssistant, registry: ClaimRegistry, entity_id: str) -> str:
    return _classify_tracked(registry, entity_id)


async def test_a_write_is_saved_without_waiting_for_shutdown(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """Through a real save, so through HA's JSON encoder too, a few seconds
    after the change."""
    registry = await _start(hass, hass_storage)
    _light(hass, "light.a", "on", **ASKED)
    await registry.async_record(ROOM, ["light.a"], "ctx-ours", targets={"light.a": ASKED})

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()

    saved = hass_storage[STORAGE_KEY]["data"]
    assert saved["claims"]["light.a"]["latest"]["context_id"] == "ctx-ours"
    assert saved["rooms"][ROOM]["lights"] == ["light.a"]


async def test_a_mismatch_noticed_after_the_restart_is_saved(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """So the grace isn't started afresh by the next restart."""
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)
    await _start(hass, hass_storage, {"light.a": _claim("ctx-ours")})

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()

    assert hass_storage[STORAGE_KEY]["data"]["claims"]["light.a"]["mismatch_since"]


async def test_lights_going_unavailable_at_shutdown_keep_their_claims(
    hass: HomeAssistant, hass_storage: dict[str, Any]
):
    """MQTT marks its lights unavailable as its connection closes."""
    _light(hass, "light.a", "on", **ASKED)
    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-ours")})
    registry._save()

    hass.set_state(CoreState.stopping)
    _light(hass, "light.a", "unavailable")
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    hass.set_state(CoreState.running)

    assert list(hass_storage[STORAGE_KEY]["data"]["claims"]) == ["light.a"]


async def test_claims_and_rooms_come_back_after_a_restart(hass: HomeAssistant, hass_storage: dict[str, Any]):
    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-ours")})

    assert set(registry.all_records()) == {"light.a"}
    assert registry.rooms_of("light.a") == [ROOM]


async def test_a_light_someone_else_had_before_the_restart_is_still_theirs(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """We asked for 200; it shows 90. Left alone at once, and an override
    once the grace has passed."""
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)

    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-ours")})

    assert _status(hass, registry, "light.a") == "mismatched"
    with after_the_grace():
        assert _status(hass, registry, "light.a") == "overridden"


async def test_a_light_overridden_before_the_restart_is_overridden_at_once(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """Its mismatch_since is restored with its claims."""
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)
    claim = {**_claim("ctx-ours"), "mismatch_since": (dt_util.utcnow() - MISMATCH_GRACE).isoformat()}

    registry = await _start(hass, hass_storage, {"light.a": claim})

    assert _status(hass, registry, "light.a") == "overridden"


async def test_a_light_unchanged_across_the_restart_is_still_ours(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """Unchanged across the restart: ours, by value."""
    _light(hass, "light.a", "on", brightness=200, color_temp_kelvin=3000)

    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-ours")})

    assert _status(hass, registry, "light.a") == "controlled"


async def test_a_restored_claim_over_a_day_old_is_dropped(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """Pruned at setup. The fresh claim beside it rules out "nothing was
    restored"."""
    registry = await _start(
        hass, hass_storage, {"light.fresh": _claim("ctx-1"), "light.stale": _claim("ctx-2", age=timedelta(days=2))}
    )

    assert set(registry.all_records()) == {"light.fresh"}


async def test_reconnecting_after_a_restart_does_not_take_the_light_back(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """A reconnect (unavailable, unknown, on, as MQTT lights do) must not
    re-baseline the light as ours."""
    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-ours")})

    _light(hass, "light.a", "unavailable")
    _light(hass, "light.a", "unknown")
    _light(hass, "light.a", "on", brightness=90, color_temp_kelvin=3000)
    await hass.async_block_till_done()

    assert _status(hass, registry, "light.a") == "mismatched"
    with freeze_time(dt_util.utcnow() + MISMATCH_GRACE, real_asyncio=True):
        assert _status(hass, registry, "light.a") == "overridden"


async def test_a_light_reconnecting_as_off_does_not_release_its_siblings(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """The first light back being off, with siblings still unknown, must not
    release the room's restored claims."""
    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-a"), "light.b": _claim("ctx-b")})

    _light(hass, "light.a", "unavailable")
    _light(hass, "light.a", "unknown")
    _light(hass, "light.b", "unavailable")
    _light(hass, "light.b", "unknown")
    _light(hass, "light.b", "off")
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.a", "light.b"}


async def test_a_room_restored_dark_lets_go_of_its_claims(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """Its lights went off while HA wasn't watching (during a restart, a
    shutdown racing FLARE's own turn-off, a restore), so no on -> off ever
    arrives to release it, and every light would read overridden."""
    _light(hass, "light.a", "off")
    _light(hass, "light.b", "off")
    released: list = []
    hass.bus.async_listen("flare_lights_released", released.append)

    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-a"), "light.b": _claim("ctx-b")})
    await hass.async_block_till_done()

    assert registry.all_records() == {}
    assert [e.data["lights"] for e in released] == [["light.a", "light.b"]]


async def test_a_room_restored_dark_waits_for_every_light_to_report(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """Lights reporting in after the claims came back, one at a time."""
    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-a"), "light.b": _claim("ctx-b")})

    _light(hass, "light.a", "unknown")
    _light(hass, "light.b", "off")
    await hass.async_block_till_done()
    assert set(registry.all_records()) == {"light.a", "light.b"}, "light.a hasn't reported yet"

    _light(hass, "light.a", "off")
    await hass.async_block_till_done()
    assert registry.all_records() == {}


async def test_a_room_restored_with_a_light_on_keeps_its_claims(hass: HomeAssistant, hass_storage: dict[str, Any]):
    _light(hass, "light.a", "on", **ASKED)
    _light(hass, "light.b", "off")

    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-a"), "light.b": _claim("ctx-b")})
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.a", "light.b"}


async def test_each_room_restored_dark_is_released_on_its_own(hass: HomeAssistant, hass_storage: dict[str, Any]):
    """A lit room keeps its claims while a dark one lets go of its own."""
    _light(hass, "light.a", "on", **ASKED)
    _light(hass, "light.b", "off")
    rooms = {
        "automation.lit": {"lights": ["light.a"], "last_seen": dt_util.utcnow().isoformat()},
        "automation.dark": {"lights": ["light.b"], "last_seen": dt_util.utcnow().isoformat()},
    }

    registry = await _start(hass, hass_storage, {"light.a": _claim("ctx-a"), "light.b": _claim("ctx-b")}, rooms)
    await hass.async_block_till_done()

    assert set(registry.all_records()) == {"light.a"}
