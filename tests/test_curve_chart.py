"""
How the curve card draws the curve itself.

This layer had no tests at all until the chart was found to be rendering
every one of its 289 samples as a separate flat-topped <rect> - which
made every ramp a visible staircase, since the samples are five minutes
apart. It is now one filled path with a gradient, and these pin the three
properties that made that change safe, none of which are obvious from
looking at the output.

The geometry is deliberately the only thing simplified. Colour is not:
brightness is piecewise linear so most sample points say nothing as
geometry, but the colour moves continuously, so the gradient still gets a
stop per sample.

Driven through node against the real card file, reusing
test_curve_js_parity.py's shims and runner - the drawing helpers are
exported for exactly this reason, as phaseAt and phaseMarks already were.
"""

import json
import re
import shutil

import pytest

from test_curve_js_parity import CARD_JS, CARD_SHIMS, _node_eval

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


DRIVER = CARD_SHIMS + f"""
const {{ simplifyPolyline, roundedTopEdge, curveFillSvg }} =
  await import({json.dumps(CARD_JS.as_posix())});

const input = JSON.parse(await new Promise((resolve) => {{
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => (buf += c));
  process.stdin.on('end', () => resolve(buf));
}}));

// The chart's own mapping, near enough: a day across the plot width.
const dayStart = input.samples[0].t;
const span = input.samples[input.samples.length - 1].t - dayStart;
const xOf = (t) => 34 + ((t - dayStart) / span) * 914;
const hOf = (b) => (b / 255) * 170;

process.stdout.write(JSON.stringify({{
  svg: curveFillSvg(input.samples, xOf, hOf, dayStart, span, 'test-gradient'),
  simplified: simplifyPolyline(input.polyline),
  keepsEnds: simplifyPolyline([{{x: 0, y: 0}}, {{x: 5, y: 0}}, {{x: 10, y: 0}}]),
  rounded: roundedTopEdge(input.corner),
  // A corner whose adjacent segments are shorter than the radius: the
  // fillet has to shrink or neighbouring curves overlap and reverse.
  tightCorner: roundedTopEdge([
    {{x: 0, y: 0}}, {{x: 2, y: 0}}, {{x: 4, y: 10}}, {{x: 6, y: 10}},
  ]),
  empty: curveFillSvg([], xOf, hOf, dayStart, span, 'g'),
  single: curveFillSvg([input.samples[0]], xOf, hOf, dayStart, span, 'g'),
}}));
"""

# A day at the real cadence: 289 samples, five minutes apart, with flat
# phases and linear ramps between them - the shape curve.py produces.
_SAMPLES = []
for _i in range(289):
    _t = _i * 300
    _hour = _t / 3600
    if _hour < 6:
        _bri, _k = 50, 2700
    elif _hour < 7:
        _f = _hour - 6
        _bri, _k = round(50 + 205 * _f), round(2700 + 7300 * _f)
    elif _hour < 17:
        _bri, _k = 255, 6667
    elif _hour < 18:
        _f = _hour - 17
        _bri, _k = round(255 - 75 * _f), round(6667 - 3467 * _f)
    else:
        _bri, _k = 180, 3200
    _SAMPLES.append({"t": _t, "brightness": _bri, "kelvin": _k})

# Flat, flat, flat, then a corner, then flat: only the corner survives.
POLYLINE = [
    {"x": 0, "y": 100},
    {"x": 10, "y": 100},
    {"x": 20, "y": 100},
    {"x": 30, "y": 50},
    {"x": 40, "y": 50},
]
CORNER = [{"x": 0, "y": 100}, {"x": 50, "y": 100}, {"x": 100, "y": 20}]


@pytest.fixture(scope="module")
def result():
    return _node_eval(DRIVER, {"samples": _SAMPLES, "polyline": POLYLINE, "corner": CORNER})


def test_the_curve_is_one_path_not_a_bar_per_sample(result):
    """The bug this replaced: 289 flat-topped <rect> columns, one per
    five-minute sample, which turned every ramp into a staircase and
    every colour change into a hard vertical band."""
    svg = result["svg"]

    assert "<rect" not in svg
    assert svg.count("<path") == 1


def test_every_sample_still_gets_its_own_colour_stop(result):
    """Only the geometry is simplified. Brightness is piecewise linear so
    most points are redundant as shape, but colour moves continuously -
    dropping stops would band the gradient."""
    assert result["svg"].count("<stop") == len(_SAMPLES)


def test_collinear_points_are_dropped_and_corners_kept(result):
    """A flat phase contributes a vertex every five minutes that says
    nothing. Dropping them is what makes the corner radius meaningful:
    the fillet is capped at half the shorter adjacent segment, so with
    every sample kept every segment would be one sample wide."""
    assert result["simplified"] == [
        {"x": 0, "y": 100},
        {"x": 20, "y": 100},
        {"x": 30, "y": 50},
        {"x": 40, "y": 50},
    ]


def test_the_first_and_last_points_always_survive(result):
    """They are the chart's own edges - the path closes to the baseline
    at each - so simplifying them away would shorten the filled area."""
    assert result["keepsEnds"] == [{"x": 0, "y": 0}, {"x": 10, "y": 0}]


def test_a_corner_is_eased_with_its_own_vertex_as_the_control_point(result):
    """The invariant that makes rounding safe at all.

    A quadratic Bezier is contained within the triangle of its three
    control points, so putting the control point ON the corner means the
    curve can only ever cut inside it. An interpolating spline through
    the sample points would instead overshoot around the flat tops and
    draw brightness the schedule never asks for - which is why the
    version before this refused to smooth at all."""
    path = result["rounded"]
    control = re.search(r"Q([\d.]+),([\d.]+)", path)

    assert control, f"no quadratic emitted: {path}"
    assert (float(control.group(1)), float(control.group(2))) == (50.0, 100.0)


def _coords(path):
    r"""Every (x, y) pair in a path string.

    The minus sign is part of the number on purpose: an earlier version
    of this matched [\d.]+ and silently read an out-of-bounds "-2.00" as
    "2.00", which made the short-segment test below pass against a
    genuinely broken fillet. Caught by mutation testing."""
    return [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", path)]


def test_the_curve_never_rises_above_the_corner_it_rounds(result):
    """The consequence of the above, stated as the thing that actually
    matters: nothing drawn is brighter than the real curve. y grows
    downward, so no coordinate may sit above the highest input point."""
    highest = min(p["y"] for p in CORNER)
    ys = [y for _, y in _coords(result["rounded"])]

    assert ys, "no coordinates parsed"
    assert min(ys) >= highest - 0.01


def test_a_short_segment_shrinks_the_fillet_rather_than_overlapping(result):
    """Capped at half of each adjacent segment. Without that, two corners
    closer together than the radius produce fillets that overlap and
    double back on themselves."""
    path = result["tightCorner"]
    xs = [x for x, _ in _coords(path)]

    assert path.count("Q") == 2
    # The input spans x = 0 to 6, and the first segment is only 2 long -
    # so an uncapped radius of 4 backs off past the start and emits a
    # negative x. Nothing may fall outside the input's own span.
    assert min(xs) >= -0.01, f"fillet ran off the start: {path}"
    assert max(xs) <= 6.01, f"fillet ran off the end: {path}"


@pytest.mark.parametrize("key", ["empty", "single"])
def test_too_few_samples_draws_nothing_rather_than_a_broken_path(result, key):
    """The card renders before the sensor's points attribute arrives, so
    both really happen."""
    assert result[key] == ""
