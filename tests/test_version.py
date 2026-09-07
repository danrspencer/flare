"""The manifest version is what HACS shows as installed, so it must not
drift from the changelog that explains it.

Checked here as well as in the release workflow because the workflow only
runs when a tag is pushed - by which point a mismatch means re-tagging.

A version may carry a prerelease suffix (0.16.0-beta.1). That is how the
two release channels are spelled: the workflow turns a hyphenated tag
into a GitHub pre-release, which HACS hides from anyone who hasn't turned
on "Show beta versions" for this repository. See CONTRIBUTING.md.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
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


def test_the_changelog_describes_the_current_version():
    """A release whose version isn't in the changelog is one nobody can
    find out anything about - including which of it is breaking, which
    for this integration has mattered more than once.

    Matched on the BASE version, so 0.16.0-beta.3 is described by the
    0.16.0 section. A section per beta would turn the changelog into a
    build log and put a commit in the way of every test build."""
    base = VERSION.fullmatch(_version()).group("base")

    assert f"## [{base}]" in CHANGELOG.read_text()


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
