"""
The custom card feature that paints a Kelvin `number` slider in the
colour temperature it sets.

Two things here are worth pinning and nothing else really is. The first
is `isSupported`: Home Assistant offers a custom feature in the tile
editor for every entity unless this says otherwise, so an over-broad
check turns up on every entity in the house, and an over-narrow one
means the feature simply never appears - neither surfaces as an error.

The second is that the gradient is the *card's* Kelvin conversion. The
whole point of this feature over a plain coloured slider is that it
agrees with the curve drawn above it in the same dashboard section; a
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
const {{ supportsKelvinFeature, kelvinGradient, labelIsDark, labelKelvin }} =
  await import({json.dumps(FEATURE_JS.as_posix())});
const {{ kelvinToRgb, rgbToHex }} = await import({json.dumps(CARD_JS.as_posix())});

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
  gradient: kelvinGradient(1000, 10000),
  narrowGradient: kelvinGradient(2000, 3000),
  reversed: kelvinGradient(10000, 1000),
  stopCount: kelvinGradient(1000, 10000, 4),
  // The card's own conversion, to compare the gradient's stops against.
  endpoints: [rgbToHex(kelvinToRgb(1000)), rgbToHex(kelvinToRgb(10000))],
  // The 8th of 16 stops (t = 7/15), plus what a plain two-point RGB
  // blend between the endpoints would put at that same position.
  sampledStop: rgbToHex(kelvinToRgb(1000 + 9000 * (7 / 15))),
  blendedStop: (() => {{
    const a = kelvinToRgb(1000);
    const b = kelvinToRgb(10000);
    const t = 7 / 15;
    return rgbToHex(a.map((v, i) => Math.round(v + (b[i] - v) * t)));
  }})(),
  dark: input.labelKelvins.map(labelIsDark),
  labelPositions: [labelKelvin(1000, 10000), labelKelvin(10000, 1000), labelKelvin(2000, 3000)],
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

LABEL_KELVINS = [1000, 2000, 3000, 6500, 10000]


@pytest.fixture(scope="module")
def result():
    return _node_eval(
        DRIVER,
        {"states": STATES, "entityIds": ENTITY_IDS, "labelKelvins": LABEL_KELVINS},
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


def test_the_gradient_uses_the_cards_own_conversion(result):
    """The reason for this feature over any coloured slider: it has to
    agree with the curve card drawn above it in the same section. Both
    ends come from kelvinToRgb, which is already parity-tested against
    curve.py, so a second copy of the conversion would fail here."""
    low, high = result["endpoints"]

    assert result["gradient"].startswith(f"linear-gradient(to right, {low} 0.00%")
    assert result["gradient"].endswith(f"{high} 100.00%)")


def test_the_gradient_is_sampled_not_a_two_point_blend(result):
    """Kelvin->RGB is not linear in RGB space - a straight blend from the
    1000K red to the 10000K blue passes through purple, which is not a
    colour any temperature on that scale is - so the stops have to be
    real samples, and this asserts the difference rather than merely
    counting them."""
    assert result["sampledStop"] in result["gradient"]
    assert result["blendedStop"] not in result["gradient"]
    assert result["gradient"].count("#") == 16


def test_the_stop_count_is_configurable(result):
    assert result["stopCount"].count("#") == 4


def test_the_gradient_tracks_the_entitys_own_range(result):
    """A narrower entity range means a narrower slice of the scale, not
    the same gradient squeezed - a 2000-3000K entity is warm end to end.
    This is what makes the feature correct for a foreign entity whose
    min/max are nothing like FLARE's."""
    assert result["narrowGradient"] != result["gradient"]
    assert result["narrowGradient"].startswith("linear-gradient(to right, ")


def test_a_reversed_range_still_runs_cold_to_warm_left_to_right(result):
    """min/max arriving the wrong way round would otherwise paint the
    track backwards while the thumb still moved left-to-right."""
    assert result["reversed"] == result["gradient"]


def test_the_value_label_flips_with_the_track_behind_it(result):
    """The track spans deep amber to pale blue, so one fixed label colour
    is unreadable at one end whichever end you choose."""
    by_kelvin = dict(zip(LABEL_KELVINS, result["dark"]))

    assert by_kelvin[1000] is False, "deep amber needs a light label"
    assert by_kelvin[10000] is True, "pale blue needs a dark label"


def test_the_label_is_coloured_for_where_it_sits_not_for_the_value(result):
    """The label is pinned to the left of the track and does not ride the
    thumb, so the colour under it is the range's low end whatever the
    value is. Colouring it by the current value instead reads correctly
    only at the bottom of the range and puts dark text on deep amber
    everywhere else - the first version did exactly that, and it was
    caught by eye rather than here, which is why this test exists."""
    full, reversed_, narrow = result["labelPositions"]

    assert full == 1000
    assert reversed_ == 1000, "min/max the wrong way round must not flip the label"
    assert narrow == 2000, "a narrow range's label sits over its own low end"


def test_the_feature_is_registered_for_the_card_editor(result):
    """Without isSupported, Home Assistant offers the feature on every
    entity in the house; without the registration it never appears in the
    editor at all, however correct the element is."""
    feature = result["feature"]

    assert feature is not None, "not pushed to window.customCardFeatures"
    assert feature["name"] == "FLARE Colour temperature"
    assert feature["hasIsSupported"]
