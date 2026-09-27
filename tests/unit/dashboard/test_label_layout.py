"""The curve card's layoutBoundaryLabels(): phase labels centred on their
boundary lines, nudged apart where they'd collide on a narrow card."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

GAP = 6
WIDTHS = [43, 20, 41, 28]  # Morning, Day, Evening, Night

CASES = {
    "phone width": {"desired": [116.5, 141.0, 288.0, 316.0], "widths": WIDTHS, "containerWidth": 315},
    "desktop, already fits": {"desired": [120.0, 200.0, 500.0, 600.0], "widths": WIDTHS, "containerWidth": 700},
    "all four within an hour": {"desired": [150.0, 154.0, 158.0, 162.0], "widths": WIDTHS, "containerWidth": 315},
    "crushed left": {"desired": [0.0, 1.0, 2.0, 3.0], "widths": WIDTHS, "containerWidth": 315},
    "crushed right": {"desired": [315.0] * 4, "widths": WIDTHS, "containerWidth": 315},
    "too narrow for all four": {"desired": [10.0, 30.0, 50.0, 70.0], "widths": WIDTHS, "containerWidth": 90},
    "single label": {"desired": [10.0], "widths": [43], "containerWidth": 315},
    "no labels": {"desired": [], "widths": [], "containerWidth": 315},
}


@pytest.fixture(scope="module")
def placed():
    results = run_js(
        f"""
const {{ layoutBoundaryLabels }} = await import({js_path(WWW / "flare-curve-card.js")});
return input.map((c) => layoutBoundaryLabels(c.desired, c.widths, c.containerWidth));""",
        list(CASES.values()),
    )
    return dict(zip(CASES, results))


def _spans(labels, widths):
    """Left/right edges of the visible labels."""
    return [(p["centre"] - w / 2, p["centre"] + w / 2) for p, w in zip(labels, widths) if not p["hidden"]]


@pytest.mark.parametrize("name", CASES)
def test_visible_labels_never_overlap(placed, name):
    edges = _spans(placed[name], CASES[name]["widths"])
    for (_, right), (left, _) in zip(edges, edges[1:]):
        assert left >= right + GAP - 0.01


@pytest.mark.parametrize("name", CASES)
def test_visible_labels_stay_inside_the_chart(placed, name):
    for left, right in _spans(placed[name], CASES[name]["widths"]):
        assert -0.01 <= left and right <= CASES[name]["containerWidth"] + 0.01


@pytest.mark.parametrize("name", CASES)
def test_labels_keep_their_order(placed, name):
    """A label that overtook its neighbour would point at the wrong line."""
    centres = [p["centre"] for p in placed[name] if not p["hidden"]]
    assert centres == sorted(centres)


def test_labels_that_already_fit_are_not_moved(placed):
    assert [p["centre"] for p in placed["desktop, already fits"]] == CASES["desktop, already fits"]["desired"]


@pytest.mark.parametrize("name", [n for n in CASES if n != "too narrow for all four"])
def test_nothing_is_dropped_when_it_fits(placed, name):
    assert not any(p["hidden"] for p in placed[name])


def test_later_labels_are_dropped_first_when_they_cannot_all_fit(placed):
    labels = placed["too narrow for all four"]
    hidden = [i for i, p in enumerate(labels) if p["hidden"]]
    visible = [i for i, p in enumerate(labels) if not p["hidden"]]
    assert hidden
    assert not visible or max(visible) < min(hidden)
