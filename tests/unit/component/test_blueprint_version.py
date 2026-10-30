"""Reading the version stamp out of a blueprint's description."""

import pytest

from custom_components.flare.blueprint_version import (
    BLUEPRINT_VERSION,
    is_outdated,
    language_from_description,
    version_from_description,
    with_language,
)


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


def test_a_copy_names_its_language_after_its_version():
    stamped = with_language("Prose.\n\nBlueprint version 1.2.3 - the integration raises a repair.", "de")

    assert "Blueprint version 1.2.3 (de) - the integration" in stamped
    assert version_from_description(stamped) == "1.2.3"
    assert language_from_description(stamped) == "de"


@pytest.mark.parametrize("description", [None, "", "Blueprint version 1.2.3 - no language"])
def test_a_copy_stamped_without_a_language_has_none(description):
    assert language_from_description(description) is None
