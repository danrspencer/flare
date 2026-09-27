"""How the curve card draws the curve: one filled path with a gradient
stop per sample, corners rounded without ever overshooting."""

import re

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node


def _sample(i):
    """A day at the real cadence, shaped like curve.py's output."""
    t = i * 300
    hour = t / 3600
    if hour < 6:
        return {"t": t, "brightness": 50, "kelvin": 2700}
    if hour < 7:
        f = hour - 6
        return {"t": t, "brightness": round(50 + 205 * f), "kelvin": round(2700 + 7300 * f)}
    if hour < 17:
        return {"t": t, "brightness": 255, "kelvin": 6667}
    if hour < 18:
        f = hour - 17
        return {"t": t, "brightness": round(255 - 75 * f), "kelvin": round(6667 - 3467 * f)}
    return {"t": t, "brightness": 180, "kelvin": 3200}


SAMPLES = [_sample(i) for i in range(289)]
# Flat, flat, flat, a corner, flat: only the corner survives simplifying.
POLYLINE = [{"x": 0, "y": 100}, {"x": 10, "y": 100}, {"x": 20, "y": 100}, {"x": 30, "y": 50}, {"x": 40, "y": 50}]
CORNER = [{"x": 0, "y": 100}, {"x": 50, "y": 100}, {"x": 100, "y": 20}]
# Segments shorter than the corner radius.
TIGHT_CORNER = [{"x": 0, "y": 0}, {"x": 2, "y": 0}, {"x": 4, "y": 10}, {"x": 6, "y": 10}]


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const {{ simplifyPolyline, roundedTopEdge, curveFillSvg }} = await import({js_path(WWW / "flare-curve-card.js")});
const dayStart = input.samples[0].t;
const span = input.samples[input.samples.length - 1].t - dayStart;
const xOf = (t) => 34 + ((t - dayStart) / span) * 914;
const hOf = (b) => (b / 255) * 170;
return {{
  svg: curveFillSvg(input.samples, xOf, hOf, dayStart, span, 'g'),
  empty: curveFillSvg([], xOf, hOf, dayStart, span, 'g'),
  single: curveFillSvg([input.samples[0]], xOf, hOf, dayStart, span, 'g'),
  simplified: simplifyPolyline(input.polyline),
  keepsEnds: simplifyPolyline([{{x: 0, y: 0}}, {{x: 5, y: 0}}, {{x: 10, y: 0}}]),
  rounded: roundedTopEdge(input.corner),
  tightCorner: roundedTopEdge(input.tight),
}};""",
        {"samples": SAMPLES, "polyline": POLYLINE, "corner": CORNER, "tight": TIGHT_CORNER},
    )


def _coords(path):
    """Every (x, y) in a path, signs included."""
    return [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", path)]


def test_the_curve_is_one_path(result):
    assert "<rect" not in result["svg"]
    assert result["svg"].count("<path") == 1


def test_every_sample_gets_its_own_colour_stop(result):
    """Only the geometry is simplified; colour varies continuously."""
    assert result["svg"].count("<stop") == len(SAMPLES)


def test_collinear_points_are_dropped_and_corners_kept(result):
    assert result["simplified"] == [{"x": 0, "y": 100}, {"x": 20, "y": 100}, {"x": 30, "y": 50}, {"x": 40, "y": 50}]


def test_the_end_points_always_survive(result):
    assert result["keepsEnds"] == [{"x": 0, "y": 0}, {"x": 10, "y": 0}]


def test_a_corner_is_rounded_with_the_corner_as_control_point(result):
    """So the curve can only cut inside the corner, never overshoot."""
    control = re.search(r"Q([\d.]+),([\d.]+)", result["rounded"])
    assert control and (float(control[1]), float(control[2])) == (50.0, 100.0)


def test_nothing_drawn_is_brighter_than_the_corner(result):
    """y grows downward."""
    ys = [y for _, y in _coords(result["rounded"])]
    assert ys and min(ys) >= min(p["y"] for p in CORNER) - 0.01


def test_a_short_segment_shrinks_the_rounding_rather_than_overlapping(result):
    path = result["tightCorner"]
    xs = [x for x, _ in _coords(path)]
    assert path.count("Q") == 2
    assert -0.01 <= min(xs) and max(xs) <= 6.01


@pytest.mark.parametrize("key", ["empty", "single"])
def test_too_few_samples_draws_nothing(result, key):
    """The card renders before the samples arrive."""
    assert result[key] == ""
