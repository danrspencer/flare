"""Versions: the manifest's placeholder, the changelog heading the release
script reads, the blueprint stamp, and release.yml (which checks tags
pushed by hand) agreeing with all three."""

import json
import re

from custom_components.flare.blueprint_version import BLUEPRINT_VERSION, version_from_description
from tests.support import COMPONENT, REPO_ROOT, load_blueprint, load_script

release = load_script("release")

MANIFEST = COMPONENT / "manifest.json"
RELEASE_WORKFLOW = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()
# Semver without build metadata, which HA/HACS's AwesomeVersion can order.
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")


def test_the_manifest_carries_the_dev_placeholder():
    """scripts/release.py writes the real version into each release."""
    assert json.loads(MANIFEST.read_text())["version"] == "0.0.0-dev"


def test_the_changelog_names_the_version_being_worked_toward():
    assert release.changelog_base((REPO_ROOT / "CHANGELOG.md").read_text()) is not None


def test_the_blueprint_stamp_matches_the_integrations_constant():
    """Disagreeing, either nobody is told about an update or everybody is
    told about one that doesn't exist - silently."""
    description = load_blueprint()["blueprint"]["description"]
    assert version_from_description(description) == BLUEPRINT_VERSION
    assert VERSION.fullmatch(BLUEPRINT_VERSION)


def test_release_yml_checks_the_real_manifest():
    assert str(MANIFEST.relative_to(REPO_ROOT)) in RELEASE_WORKFLOW


def test_release_yml_checks_the_stamp_against_the_tag():
    assert '[ "$constant" != "$tag" ] || [ "$description" != "$tag" ]' in RELEASE_WORKFLOW
    assert "blueprint_version.BLUEPRINT_VERSION" in RELEASE_WORKFLOW


def test_release_yml_publishes_a_beta_as_a_prerelease():
    """A beta published as a normal release reaches every user."""
    assert "prerelease=true" in RELEASE_WORKFLOW
    assert "--prerelease" in RELEASE_WORKFLOW


def test_release_yml_checks_the_changelog_by_base_version():
    """So a beta doesn't need its own changelog section."""
    assert "steps.channel.outputs.base" in RELEASE_WORKFLOW
