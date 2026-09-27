"""Reading the version stamp out of a blueprint's description."""

import pytest

from custom_components.flare.blueprint_version import BLUEPRINT_VERSION, is_outdated, version_from_description


def test_the_version_is_found_in_running_prose():
    text = "FLARE: lighting.\n\nBlueprint version 1.2.3 - the integration raises a repair.\n"
    assert version_from_description(text) == "1.2.3"


def test_a_prerelease_stamp_parses_whole():
    assert version_from_description("Blueprint version 0.16.0-beta.2") == "0.16.0-beta.2"


@pytest.mark.parametrize("description", [None, "", "Some blueprint, no stamp here"])
def test_no_stamp_reads_as_no_version(description):
    assert version_from_description(description) is None


def test_only_this_releases_version_is_current():
    """Inequality, so an abandoned beta or no stamp is outdated too."""
    assert not is_outdated(BLUEPRINT_VERSION)
    assert is_outdated("0.0.1")
    assert is_outdated("99.0.0")
    assert is_outdated(None)
