"""The blueprint repairs, against real blueprints loaded in HA: reading
the blueprint store, "is anything using it", and a blueprint that fails
to load. Only in-use copies count, since a GitHub import lands under
the owner's name and can leave an orphan at the other path."""

import shutil
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.flare.blueprint_check import (
    ISSUE_ID,
    MISSING_ISSUE_ID,
    async_check,
    blueprint_is_installed,
    outdated_blueprints,
)
from custom_components.flare.const import DOMAIN
from tests.support import BLUEPRINT_PATH, REPO_ROOT


@pytest.fixture
def hass_config_dir(tmp_path) -> str:
    """Copies blueprints/ rather than symlinking it: these tests write
    blueprint files, which would otherwise land in the repo."""
    (tmp_path / "custom_components").symlink_to(REPO_ROOT / "custom_components")
    shutil.copytree(REPO_ROOT / "blueprints", tmp_path / "blueprints")
    return str(tmp_path)


STALE = """\
blueprint:
  name: FLARE
  description: >
    An older copy.


    Blueprint version 0.0.1 - the integration raises a repair when a
    newer one is available.
  domain: automation
  source_url: https://github.com/danrspencer/flare/blob/main/blueprints/automation/danrspencer/flare.yaml
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

    _write(hass, BLUEPRINT_PATH, (REPO_ROOT / "blueprints" / "automation" / BLUEPRINT_PATH).read_text())
    await async_check(hass)

    assert _issues(hass) == set()
