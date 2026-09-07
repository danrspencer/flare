"""
The custom card feature that paints a Kelvin `number` slider in the
colour temperature it sets.

Two things here are worth pinning and nothing else really is. The first
is `isSupported`: Home Assistant offers a custom feature in the tile
editor for every entity unless this says otherwise, so an over-broad
check turns up on every entity in the house, and an over-narrow one
means the feature simply never appears - neither surfaces as an error.

The second is that the bar is painted from the *card's* Kelvin
conversion, at the current value. That is the entire feature - it has to
agree with the curve drawn above it in the same dashboard section, and a
second, drifting copy of the conversion would look fine and be subtly
wrong, which is exactly the failure a test is for.

Driven through node against the real feature file, reusing
test_curve_js_parity.py's shims and runner. The DOM is deliberately not
exercised - the element is only constructed by a live frontend, and a
fake DOM good enough to prove anything about a range input would be a
bigger lie than no test at all. The pure functions carry the logic
precisely so that is a reasonable line to draw.
"""

import json
import shutil

import pytest

from test_curve_js_parity import CARD_JS, CARD_SHIMS, _node_eval

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

FEATURE_JS = CARD_JS.parent / "flare-kelvin-feature.js"


DRIVER = CARD_SHIMS + f"""
const {{ supportsKelvinFeature, sliderBackground, valueFraction }} =
  await import({json.dumps(FEATURE_JS.as_posix())});
const {{ kelvinToRgb }} = await import({json.dumps(CARD_JS.as_posix())});

const input = JSON.parse(await new Promise((resolve) => {{
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => (buf += c));
  process.stdin.on('end', () => resolve(buf));
}}));

const hass = {{ states: input.states }};

process.stdout.write(JSON.stringify({{
  supported: input.entityIds.map((id) => supportsKelvinFeature(hass, {{ entity_id: id }})),
  noContext: supportsKelvinFeature(hass, undefined),
  emptyContext: supportsKelvinFeature(hass, {{}}),
  // The same value painted at three points of the same range, plus the
  // card's own conversion for each, so the test can assert the bar is
  // that colour rather than merely "some colour".
  backgrounds: input.paintCases.map((c) => sliderBackground(c.k, valueFraction(c.k, c.min, c.max))),
  rgbs: input.paintCases.map((c) => kelvinToRgb(c.k)),
  fractions: input.fractionCases.map((c) => valueFraction(c[0], c[1], c[2])),
  feature: (() => {{
    const entry = globalThis.window.customCardFeatures.find(
      (f) => f.type === 'flare-kelvin-feature'
    );
    return entry
      ? {{ name: entry.name, hasIsSupported: typeof entry.isSupported === 'function' }}
      : null;
  }})(),
}}));
"""

KELVIN_NUMBER = {
    "entity_id": "number.downstairs_morning_kelvin",
    "state": "10000",
    "attributes": {"unit_of_measurement": "K", "min": 1000, "max": 10000, "step": 1},
}
BRIGHTNESS_NUMBER = {
    "entity_id": "number.downstairs_morning_brightness",
    "state": "255",
    "attributes": {"min": 0, "max": 255, "step": 1},
}
TRANSITION_NUMBER = {
    "entity_id": "number.downstairs_morning_kelvin_transition",
    "state": "30",
    "attributes": {"unit_of_measurement": "min", "min": 0, "max": 1440, "step": 1},
}
# A Kelvin-valued sensor rather than a number: right unit, wrong domain,
# and nothing to set - the feature would render a slider that cannot
# write. Pins the domain check independently of the unit check.
KELVIN_SENSOR = {
    "entity_id": "sensor.some_colour_temp",
    "state": "4000",
    "attributes": {"unit_of_measurement": "K"},
}
# Someone else's Kelvin number entity. This one SHOULD be supported -
# the feature is keyed on the unit precisely so it works beyond FLARE.
FOREIGN_KELVIN = {
    "entity_id": "number.some_other_integration_temp",
    "state": "3000",
    "attributes": {"unit_of_measurement": "K", "min": 2000, "max": 6500, "step": 100},
}

STATES = {s["entity_id"]: s for s in (
    KELVIN_NUMBER,
    BRIGHTNESS_NUMBER,
    TRANSITION_NUMBER,
    KELVIN_SENSOR,
    FOREIGN_KELVIN,
)}
ENTITY_IDS = list(STATES)

# Bottom, middle and top of one range, so the colour and the fill point
# can be checked as moving together.
PAINT_CASES = [
    {"k": 1000, "min": 1000, "max": 10000},
    {"k": 5500, "min": 1000, "max": 10000},
    {"k": 10000, "min": 1000, "max": 10000},
]

FRACTION_CASES = [
    (5500, 1000, 10000),  # midpoint
    (500, 1000, 10000),  # below the range
    (99999, 1000, 10000),  # above it
    (2500, 2000, 3000),  # a narrower range of its own
    (4000, 4000, 4000),  # degenerate: min == max
]


@pytest.fixture(scope="module")
def result():
    return _node_eval(
        DRIVER,
        {
            "states": STATES,
            "entityIds": ENTITY_IDS,
            "paintCases": PAINT_CASES,
            "fractionCases": [list(c) for c in FRACTION_CASES],
        },
    )


def _supported(result):
    return dict(zip(ENTITY_IDS, result["supported"]))


def test_a_kelvin_number_is_supported(result):
    assert _supported(result)["number.downstairs_morning_kelvin"] is True


def test_any_kelvin_number_is_supported_not_just_flares(result):
    """Keyed on unit_of_measurement rather than the entity_id shape, so
    the feature is useful to anyone with a Kelvin-valued number and
    cannot go stale if this integration's naming changes."""
    assert _supported(result)["number.some_other_integration_temp"] is True


@pytest.mark.parametrize(
    "entity_id",
    [
        "number.downstairs_morning_brightness",
        "number.downstairs_morning_kelvin_transition",
    ],
)
def test_the_other_number_entities_are_not_supported(result, entity_id):
    """Both are `number` entities on the same device - brightness carries
    no unit and a transition is in minutes. Without the unit check the
    feature would be offered for every control in the section."""
    assert _supported(result)[entity_id] is False


def test_a_kelvin_sensor_is_not_supported(result):
    """Right unit, wrong domain: there is nothing to set, so the slider
    would be unwritable. Pins the domain check on its own, since every
    other rejected case above is rejected on the unit."""
    assert _supported(result)["sensor.some_colour_temp"] is False


def test_a_missing_or_empty_context_is_not_supported(result):
    """A card feature can be rendered before its parent card has resolved
    an entity, so both of these really happen."""
    assert result["noContext"] is False
    assert result["emptyContext"] is False


def test_the_bar_is_a_solid_fill_in_the_colour_of_the_current_value(result):
    """The whole feature. The bar is one solid colour - the colour of the
    value it is set to - not a gradient across the range: an earlier
    version painted the full warm-to-cool sweep and read as a colour
    picker rather than as one of a column of matching sliders."""
    for background, rgb in zip(result["backgrounds"], result["rgbs"]):
        fill = "rgb({}, {}, {})".format(*rgb)

        assert background.count(fill) == 2, f"expected two hard stops of {fill}"
        assert background.startswith(f"linear-gradient(to right, {fill} 0%"), background


def test_the_two_stops_meet_at_the_fill_point_with_no_blend(result):
    """A fill level, not a gradient: both stops sit at the same position,
    so the edge is crisp. A single stop either side would fade the bar
    across its whole width."""
    low, mid, high = result["backgrounds"]

    assert "0.00%, rgba(" in low, "at the bottom of the range the bar is empty"
    assert "100.00%, rgba(" in high, "at the top it is full"
    assert "50.00%, rgba(" in mid


def test_the_unfilled_remainder_is_neutral_not_tinted(result):
    """The one place this deliberately departs from the built-in slider,
    which tints its remainder with its own colour.

    An honest orange-to-blue colour-temperature ramp has to pass through
    white in the middle - 6667K, FLARE's own Day default, is very nearly
    white - so a white fill above a white-tinted remainder on a white
    tile is an invisible control. A neutral remainder keeps the fill edge
    legible at every temperature, including the pale ones."""
    for background, rgb in zip(result["backgrounds"], result["rgbs"]):
        assert "rgba(128, 128, 128, 0.18)" in background, background
        assert "rgba({}, {}, {}".format(*rgb) not in background, background


def test_the_colour_actually_moves_with_the_value(result):
    """Guards the case the tests above would all still pass on: a bar
    painted from a fixed colour rather than the current value."""
    low, mid, high = result["backgrounds"]

    assert low != mid != high
    assert len({tuple(rgb) for rgb in result["rgbs"]}) == 3


def test_the_fill_point_is_clamped_to_the_entitys_own_range(result):
    """A `number` can report outside its own min/max - a restored value
    from before the range changed, say - and an unclamped fraction paints
    a stop at -5% or 300%, which CSS renders as a bar that is simply
    wrong rather than as an error."""
    mid, below, above, narrow, degenerate = result["fractions"]

    assert mid == 0.5
    assert below == 0
    assert above == 1
    assert narrow == 0.5
    assert degenerate == 0, "min == max must not divide by zero"


def test_the_feature_is_registered_for_the_card_editor(result):
    """Without isSupported, Home Assistant offers the feature on every
    entity in the house; without the registration it never appears in the
    editor at all, however correct the element is."""
    feature = result["feature"]

    assert feature is not None, "not pushed to window.customCardFeatures"
    assert feature["name"] == "FLARE Colour temperature"
    assert feature["hasIsSupported"]
