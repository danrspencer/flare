"""Deprecated blueprint inputs, and the release that removes them."""

import pytest

from tests.support import REPO_ROOT, load_blueprint, load_script

release = load_script("release")

# Every deprecated input, by the major version that removes it.
REMOVED_IN = {
    "use_area_sensors": 3,
    "extra_triggers": 3,
}


def _inputs(inputs: dict) -> dict:
    """Every input, sections' own included, by key."""
    found = {}
    for key, value in inputs.items():
        if "input" in value:
            found.update(_inputs(value["input"]))
        else:
            found[key] = value
    return found


INPUTS = _inputs(load_blueprint()["blueprint"]["input"])


def test_every_deprecated_input_is_listed():
    deprecated = {key for key, value in INPUTS.items() if value["name"].endswith("(Deprecated)")}
    assert deprecated == set(REMOVED_IN)


@pytest.mark.parametrize("key", sorted(REMOVED_IN))
def test_a_deprecated_input_is_gone_by_the_release_that_removes_it(key):
    """Raising the changelog to that release fails here until the input,
    and everything reading it, is deleted (see CLAUDE.md's 3.0 plan)."""
    major = release.parse_base(release.changelog_base((REPO_ROOT / "CHANGELOG.md").read_text()))[0]
    assert major < REMOVED_IN[key] or key not in INPUTS, (
        f"{key} is deprecated for removal in {REMOVED_IN[key]}.0: delete it"
    )
