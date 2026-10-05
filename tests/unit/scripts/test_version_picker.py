"""The docs' version picker: which version a page is, what it offers, and
where each choice goes."""

import pytest

from tests.support import REPO_ROOT
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

PICKER = REPO_ROOT / "docs" / "_versions" / "picker.js"
RELEASED = {"latest": "1.1.0", "releases": ["1.1.0", "1.0.0"], "beta": "1.2.0-beta.3"}
UNRELEASED = {"latest": "1.0.0-beta.13", "releases": [], "beta": "1.0.0-beta.13"}


def _picker(calls: str, versions: dict):
    return run_js(
        f"""
await import({js_path(PICKER)});
const {{ locate, options, notice }} = globalThis.FlareVersions;
const versions = input;
return {calls};
""",
        versions,
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/flare/installation/", {"kind": "latest", "version": "1.1.0", "rest": "installation/"}),
        ("/flare/v/1.0.0/installation/", {"kind": "release", "version": "1.0.0", "rest": "installation/"}),
        ("/flare/beta/reference/zones/", {"kind": "beta", "version": "1.2.0-beta.3", "rest": "reference/zones/"}),
    ],
)
def test_a_page_knows_which_version_it_is(path, expected):
    assert _picker(f"locate({path!r}, '/flare/', versions)", RELEASED) == expected


def test_each_choice_goes_to_the_same_page_in_that_version():
    choices = _picker("options('/flare/', versions, 'installation/')", RELEASED)

    assert choices == [
        {"version": "1.1.0", "label": "1.1.0 (latest)", "url": "/flare/installation/"},
        {"version": "1.0.0", "label": "1.0.0", "url": "/flare/v/1.0.0/installation/"},
        {"version": "1.2.0-beta.3", "label": "1.2.0-beta.3 (beta)", "url": "/flare/beta/installation/"},
    ]


def test_with_no_release_the_beta_is_at_the_root():
    choices = _picker("options('/flare/', versions, '')", UNRELEASED)

    assert choices == [{"version": "1.0.0-beta.13", "label": "1.0.0-beta.13 (beta)", "url": "/flare/"}]


@pytest.mark.parametrize(
    ("path", "versions", "says"),
    [
        ("/flare/installation/", RELEASED, None),
        ("/flare/v/1.0.0/", RELEASED, "These are the docs for FLARE 1.0.0."),
        ("/flare/beta/", RELEASED, "These are the docs for the beta, 1.2.0-beta.3."),
        ("/flare/", UNRELEASED, "There's no release yet: these are the docs for the beta, 1.0.0-beta.13."),
    ],
)
def test_a_page_that_isnt_the_latest_release_says_so(path, versions, says):
    result = _picker(f"notice(locate({path!r}, '/flare/', versions), versions)", versions)

    assert (result and result["text"]) == says
