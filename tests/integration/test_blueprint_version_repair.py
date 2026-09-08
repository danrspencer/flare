"""
The out-of-date-blueprint check, against a real Home Assistant with real
blueprints loaded.

This is the layer that can catch what the pure tests structurally
cannot: that we read Home Assistant's blueprint store correctly, that
"is anyone actually using this?" answers truthfully, and that a
blueprint which failed to load doesn't take the check down with it.

The orphan rule is the one most worth pinning. Importing from GitHub
installs under the repository OWNER's name, which is not the folder name
in this repo, so a house can genuinely end up with two copies at two
paths - and Home Assistant never removes the one you stopped using. A
check that reported it would be nagging about a file nothing reads, and
the user would have no way to make it stop.
"""

import shutil
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.flare.blueprint_check import outdated_blueprints

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def hass_config_dir(tmp_path) -> str:
    """Overrides the suite's own fixture to COPY blueprints/ rather than
    symlink it.

    This is the only module that writes blueprint files, and the shared
    fixture symlinks the real directory - so writing through it lands
    the test's fixtures in the actual repository. That is not
    hypothetical: it happened while this module was being written, and
    four junk blueprints were staged for commit before anyone noticed.
    Everything else about the fixture is unchanged."""
    (tmp_path / "custom_components").symlink_to(REPO_ROOT / "custom_components")
    shutil.copytree(REPO_ROOT / "blueprints", tmp_path / "blueprints")
    return str(tmp_path)

BLUEPRINT_PATH = "danspencer/flare.yaml"

STALE = """\
blueprint:
  name: FLARE
  description: >
    An older copy.


    Blueprint version 0.0.1 - the integration raises a repair when a
    newer one is available.
  domain: automation
  source_url: https://github.com/danrspencer/flare/blob/main/blueprints/automation/danspencer/flare.yaml
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
    # Load-bearing. An automation whose blueprint rejects its inputs
    # simply doesn't appear, and then it uses no blueprint - so a test
    # asserting "this blueprint isn't reported" would pass for having no
    # consumer rather than for the version being current. That is
    # exactly what happened here before this assert existed.
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
    """The orphan rule - see the module docstring. Home Assistant leaves
    an unreferenced blueprint on disk forever, and telling someone to
    update a file no automation reads is noise they cannot silence."""
    _write(hass, "orphan/flare.yaml", STALE)
    assert await async_setup_component(hass, "automation", {})
    await hass.async_block_till_done()

    assert await outdated_blueprints(hass) == []


async def test_somebody_elses_blueprint_is_left_alone(hass: HomeAssistant):
    """Offering to overwrite a stranger's blueprint with ours would be
    considerably worse than missing an update."""
    _write(hass, "someone/other.yaml", FOREIGN)
    await _automation_using(hass, "someone/other.yaml", "theirs")

    assert await outdated_blueprints(hass) == []


async def test_the_shipped_blueprint_reports_nothing(hass: HomeAssistant):
    """The real blueprint, symlinked in by conftest, carries the version
    the integration expects - so a fresh install is quiet. Fails if the
    stamp and the constant ever drift, from the other direction to the
    pure test."""
    await _automation_using(hass, BLUEPRINT_PATH, "room")

    assert await outdated_blueprints(hass) == []


async def test_a_broken_blueprint_does_not_break_the_check(hass: HomeAssistant):
    """async_get_blueprints returns the EXCEPTION for a blueprint that
    failed to load, not a Blueprint. Treating that as a blueprint would
    raise inside a check that is only advisory, taking out the repair
    for everyone else's copies too."""
    _write(hass, "broken/flare.yaml", "blueprint: {this is not: valid}\n")
    _write(hass, "stale/flare.yaml", STALE)
    await _automation_using(hass, "stale/flare.yaml", "room")

    outdated = await outdated_blueprints(hass)

    assert [b.path for b in outdated] == ["stale/flare.yaml"]
