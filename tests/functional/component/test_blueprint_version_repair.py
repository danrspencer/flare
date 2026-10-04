"""The blueprint repairs, against real blueprints loaded in HA: reading
the blueprint store, "is anything using it", and a blueprint that fails
to load. Only in-use copies count, since an unused copy at another
path is never removed."""

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.flare.blueprint_check import (
    ISSUE_ID,
    MISSING_ISSUE_ID,
    INSTALL_PATH,
    async_check,
    async_install_blueprint,
    async_update_blueprints,
    blueprint_is_installed,
    outdated_blueprints,
)
from custom_components.flare.blueprint_version import BLUEPRINT_VERSION, version_from_description
from custom_components.flare.const import DOMAIN
from tests.support import BLUEPRINT_FILE, BLUEPRINT_PATH


STALE = """\
blueprint:
  name: FLARE
  description: >
    An older copy.


    Blueprint version 0.0.1 - the integration raises a repair when a
    newer one is available.
  domain: automation
  input: {}
triggers: []
actions: []
"""

FOREIGN = """\
blueprint:
  name: Somebody else's blueprint
  description: Nothing to do with us.
  domain: automation
  input: {}
triggers: []
actions: []
"""


def _write(hass: HomeAssistant, path: str, content: str) -> None:
    target = Path(hass.config.config_dir) / "blueprints" / "automation" / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


async def _automation_using(hass: HomeAssistant, path: str, alias: str, **input_) -> None:
    assert await async_setup_component(
        hass,
        "automation",
        {"automation": [{"alias": alias, "use_blueprint": {"path": path, "input": input_}}]},
    )
    await hass.async_block_till_done()
    # An automation that rejects its inputs silently doesn't exist, and
    # "not reported" would then pass for the wrong reason.
    assert hass.states.get(f"automation.{alias}") is not None, (
        f"{alias} failed to set up from {path}, so it is using no blueprint"
    )


async def test_a_stale_blueprint_in_use_is_reported(hass: HomeAssistant):
    _write(hass, "stale/flare.yaml", STALE)
    await _automation_using(hass, "stale/flare.yaml", "room")

    outdated = await outdated_blueprints(hass)

    assert [(b.path, b.version) for b in outdated] == [("stale/flare.yaml", "0.0.1")]
    assert outdated[0].automations == 1


async def test_a_stale_blueprint_nothing_uses_is_not_reported(hass: HomeAssistant):
    _write(hass, "orphan/flare.yaml", STALE)
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()

    assert await outdated_blueprints(hass) == []


async def test_somebody_elses_blueprint_is_left_alone(hass: HomeAssistant):
    _write(hass, "someone/other.yaml", FOREIGN)
    await _automation_using(hass, "someone/other.yaml", "theirs")

    assert await outdated_blueprints(hass) == []


async def test_the_shipped_blueprint_reports_nothing(hass: HomeAssistant):
    await _automation_using(hass, BLUEPRINT_PATH, "room")

    assert await outdated_blueprints(hass) == []


async def test_a_broken_blueprint_does_not_break_the_check(hass: HomeAssistant):
    """HA returns the exception for a blueprint that failed to load."""
    _write(hass, "broken/flare.yaml", "blueprint: {this is not: valid}\n")
    _write(hass, "stale/flare.yaml", STALE)
    await _automation_using(hass, "stale/flare.yaml", "room")

    outdated = await outdated_blueprints(hass)

    assert [b.path for b in outdated] == ["stale/flare.yaml"]


# --- No blueprint at all ------------------------------------------------


def _remove_ours(hass: HomeAssistant) -> None:
    (Path(hass.config.config_dir) / "blueprints" / "automation" / BLUEPRINT_PATH).unlink()


async def test_a_house_with_no_blueprint_reports_it_missing(hass: HomeAssistant):
    _remove_ours(hass)
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()

    assert await blueprint_is_installed(hass) is False


async def test_an_installed_but_unused_blueprint_still_counts(hass: HomeAssistant):
    """Mid-setup, not missing."""
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()

    assert await blueprint_is_installed(hass) is True
    assert await outdated_blueprints(hass) == []


async def test_somebody_elses_blueprint_does_not_count_as_ours(hass: HomeAssistant):
    _remove_ours(hass)
    _write(hass, "someone/other.yaml", FOREIGN)
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()

    assert await blueprint_is_installed(hass) is False


# --- Which repair gets raised -------------------------------------------


def _issues(hass: HomeAssistant) -> set[str]:
    return {
        issue_id
        for (domain, issue_id) in ir.async_get(hass).issues
        if domain == DOMAIN
    }


async def test_no_blueprint_raises_missing_and_not_outdated(hass: HomeAssistant):
    _remove_ours(hass)
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()

    await async_check(hass)

    assert _issues(hass) == {MISSING_ISSUE_ID}


async def test_a_stale_blueprint_raises_outdated_and_not_missing(hass: HomeAssistant):
    _remove_ours(hass)
    _write(hass, "stale/flare.yaml", STALE)
    await _automation_using(hass, "stale/flare.yaml", "room")

    await async_check(hass)

    assert _issues(hass) == {ISSUE_ID}


async def test_installing_clears_the_missing_repair(hass: HomeAssistant):
    _remove_ours(hass)
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()
    await async_check(hass)
    assert _issues(hass) == {MISSING_ISSUE_ID}

    _write(hass, BLUEPRINT_PATH, BLUEPRINT_FILE.read_text())
    await async_check(hass)

    assert _issues(hass) == set()


# --- Fix ------------------------------------------------------------------


def _installed_version(hass: HomeAssistant, path: str) -> str | None:
    text = (Path(hass.config.config_dir) / "blueprints" / "automation" / path).read_text()
    return version_from_description(text)


async def test_fix_installs_the_shipped_blueprint(hass: HomeAssistant):
    _remove_ours(hass)
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()

    assert await async_install_blueprint(hass) == INSTALL_PATH

    assert _installed_version(hass, INSTALL_PATH) == BLUEPRINT_VERSION
    await async_check(hass)
    assert _issues(hass) == set()


async def test_fix_updates_a_stale_copy_where_it_was_found(hass: HomeAssistant):
    _remove_ours(hass)
    _write(hass, "stale/flare.yaml", STALE)
    await _automation_using(hass, "stale/flare.yaml", "room")

    assert await async_update_blueprints(hass) == ["stale/flare.yaml"]

    assert _installed_version(hass, "stale/flare.yaml") == BLUEPRINT_VERSION
