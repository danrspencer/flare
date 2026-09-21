"""The version HACS shows as installed comes out of the release's own
manifest.json, and that is written when the release is built, not typed
into the source. So these tests are about the seams: the source carries
the placeholder, the changelog names the version being worked toward, and
release.yml - which still checks any tag pushed by hand - agrees with the
manifest's location.

A version may carry a prerelease suffix (0.16.0-beta.1). That is how the
two release channels are spelled: the workflow turns a hyphenated tag
into a GitHub pre-release, which HACS hides from anyone who hasn't turned
on "Show beta versions" for this repository. See CONTRIBUTING.md.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "flare"))

import release  # noqa: E402
from const import DEV_VERSION  # noqa: E402

MANIFEST = REPO_ROOT / "custom_components" / "flare" / "manifest.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"

# Semver, with the prerelease part optional. Deliberately not a full
# semver regex: build metadata (+foo) is not used here and AwesomeVersion,
# which is what Home Assistant and HACS actually compare with, has its own
# ideas about it.
VERSION = re.compile(r"(?P<base>\d+\.\d+\.\d+)(?:-(?P<prerelease>[0-9A-Za-z.-]+))?")


def _version() -> str:
    return json.loads(MANIFEST.read_text())["version"]


def test_manifest_version_is_orderable():
    """HACS compares versions with AwesomeVersion to decide whether an
    update exists, so the shape has to be one it can order - including
    ordering a beta below the release it precedes."""
    assert VERSION.fullmatch(_version()), _version()


def test_the_source_carries_the_placeholder_version():
    """A release is built on the side by scripts/release.py, which writes
    the real version into a copy of the tree. A number typed into the
    source would be overwritten, so it can only mislead - failing here
    catches a hand-bump made out of the old habit."""
    assert _version() == DEV_VERSION


def test_the_changelog_names_the_version_being_worked_toward():
    """The release script reads the target version from the top section's
    heading, so that heading is what a person is really deciding when they
    write it. Without a parseable one nothing can be cut.

    A release's changelog section is still required, and checked at tag
    time by release.yml - by construction it exists for anything the
    script builds, because that is where the version came from."""
    assert release.changelog_base(CHANGELOG.read_text()) is not None


def test_the_release_workflow_checks_the_same_manifest_this_test_does():
    """The workflow greps a hardcoded path. If the component directory is
    ever renamed and only one of them is updated, releases start passing
    a check that reads a file that no longer exists."""
    assert str(MANIFEST.relative_to(REPO_ROOT)) in RELEASE_WORKFLOW.read_text()


def test_the_release_workflow_can_publish_a_prerelease():
    """The failure this guards is the expensive one and it is silent: a
    beta tag published as an ordinary release goes straight to every
    tester, which is the exact thing the two channels exist to prevent,
    and nothing about the release would look wrong afterwards.

    Asserted against the workflow text because the rule lives in shell -
    a hyphen in the tag - and there is no way to run the workflow from
    here. What can go stale is the wiring, so that is what is pinned:
    the channel step must still produce the flag, and the release step
    must still pass it."""
    workflow = RELEASE_WORKFLOW.read_text()

    assert "prerelease=true" in workflow, "nothing decides the channel"
    assert "--prerelease" in workflow, "the channel is decided but never passed to gh"


def test_the_changelog_check_uses_the_base_version():
    """Guards the half of the channel logic the test above doesn't: if
    the workflow went back to grepping the full tag, every beta would
    need its own changelog section and the first one would fail the
    release rather than publish wrongly."""
    assert "steps.channel.outputs.base" in RELEASE_WORKFLOW.read_text()
