"""
The version stamp that tells a user their blueprint has fallen behind.

Two halves of FLARE deploy separately - HACS updates the integration,
and the blueprint has to be re-imported - so the stamp is the only
signal that they have drifted. It is also the only part of this that
lives in two files at once (a constant in Python, a sentence in YAML),
which makes them disagreeing the obvious way for this to rot: a stale
stamp raises no repair and no error, it simply never tells anyone.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "flare"))

from blueprint_version import (  # noqa: E402
    BLUEPRINT_VERSION,
    is_outdated,
    version_from_description,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BLUEPRINT = REPO_ROOT / "blueprints" / "automation" / "danspencer" / "flare.yaml"


class _Loader(yaml.SafeLoader):
    """The blueprint is full of `!input`, which plain SafeLoader refuses."""


_Loader.add_constructor("!input", lambda loader, node: None)


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return yaml.load(BLUEPRINT.read_text(), _Loader)["blueprint"]


# --- The two copies must agree -----------------------------------------


def test_the_blueprint_carries_the_version_the_integration_expects(blueprint):
    """THE test in this file. The constant is what the integration
    compares against; the description is what every installed copy
    carries. If they disagree, either nobody is ever told about an
    update, or everybody is told about one that doesn't exist - and
    neither shows up as an error anywhere."""
    assert version_from_description(blueprint["description"]) == BLUEPRINT_VERSION


def test_the_version_is_orderable(blueprint):
    """Same shape as the manifest's, so a beta stamp sorts under the
    release it precedes and the tag the fix downloads actually exists."""
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", BLUEPRINT_VERSION)


def test_the_stamp_is_visible_to_a_user_reading_the_description(blueprint):
    """It lives in the description because the blueprint schema has no
    field for it (see blueprint_version.py). That is a constraint, but
    the version being human-readable in the automation editor is a real
    benefit, so it should stay a sentence rather than becoming a
    machine-only marker."""
    assert "Blueprint version" in blueprint["description"]


# --- Parsing -----------------------------------------------------------


def test_an_unstamped_description_reads_as_no_version():
    """Every copy released before this existed. It has to parse as
    "update me" rather than raising, because that is the population the
    check is for on the day it ships."""
    assert version_from_description("Some blueprint, no stamp here") is None
    assert is_outdated(None)


@pytest.mark.parametrize("description", [None, ""])
def test_a_missing_description_is_not_an_error(description):
    """`description` is optional in the blueprint schema, so a blueprint
    without one is legal and must not blow up the check."""
    assert version_from_description(description) is None


def test_the_version_is_found_in_running_prose():
    """It sits in a sentence in a paragraph, not on a line of its own,
    so the parse cannot depend on line position."""
    text = "FLARE: lighting.\n\nBlueprint version 1.2.3 - the integration raises a repair.\n"

    assert version_from_description(text) == "1.2.3"


def test_a_prerelease_stamp_parses_whole():
    """A blueprint changed during a beta carries the beta's version, and
    truncating it at the hyphen would silently compare 0.16.0-beta.1 as
    0.16.0 - which is a DIFFERENT blueprint."""
    assert version_from_description("Blueprint version 0.16.0-beta.2") == "0.16.0-beta.2"


def test_only_the_current_version_is_up_to_date():
    """Deliberately an inequality rather than "older than". Someone left
    on an abandoned beta is running a blueprint that no release ships,
    and should be moved back onto the released one."""
    assert not is_outdated(BLUEPRINT_VERSION)
    assert is_outdated("0.0.1")
    assert is_outdated("99.0.0")


# --- The release-time guards -------------------------------------------

RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_a_stable_release_cannot_ship_a_beta_stamped_blueprint():
    """If the blueprint changes during a beta, the stamp holds that
    beta's version - and promoting without moving it would point every
    STABLE user's Fix button at a beta blueprint, quietly undoing the
    two channels. Silent until somebody presses Fix, so it is checked
    where the channel is already known: at tag time."""
    workflow = RELEASE_WORKFLOW.read_text()

    assert "stamp_is_beta" in workflow, "nothing classifies the stamp"
    assert 'PRERELEASE" = "false" ] && [ "$stamp_is_beta" = "true"' in workflow


def test_the_stamp_must_name_a_tag_that_exists():
    """The stamp names the tag the Fix button downloads from. A stamp
    naming a tag that was never cut - a typo, or a bump that got ahead
    of its release - makes Fix fail with a download error the user can
    do nothing about."""
    workflow = RELEASE_WORKFLOW.read_text()

    assert "git ls-remote --exit-code --tags origin" in workflow


def test_the_release_workflow_reads_the_stamp_from_its_one_source():
    """Re-deriving it from the blueprint YAML, or hardcoding it in the
    workflow, would give the release a second opinion about the version
    that the tests don't pin."""
    assert "blueprint_version.BLUEPRINT_VERSION" in RELEASE_WORKFLOW.read_text()

