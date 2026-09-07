"""
The custom card feature that paints a Kelvin `number` slider in the
colour temperature it sets.

Two things here are worth pinning and nothing else really is. The first
is `isSupported`: Home Assistant offers a custom feature in the tile
editor for every entity unless this says otherwise, so an over-broad
check turns up on every entity in the house, and an over-narrow one
means the feature simply never appears - neither surfaces as an error.

The second is that the fill is painted from the *card's* Kelvin
conversion, at the current value. That is the entire feature - it has to
agree with the curve drawn above it in the same dashboard section, and a
second, drifting copy of the conversion would look fine and be subtly
wrong, which is exactly the failure a test is for.

Everything else - the handle, the rounded fill cap, the tooltip, drag and
keyboard behaviour - is ha-control-slider's, not ours, so there is
nothing here worth pinning about it. The one thing that IS ours and does
matter is that we set the same custom properties the frontend's own
cardFeatureStyles sets, so the slider matches the built-in one beside it;
that is asserted against the style text rather than a rendered tile.

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
# The slider machinery both features share. The CSS and the per-value
# setProperty calls live here now, not in the feature.
SLIDER_JS = CARD_JS.parent / "flare-value-slider.js"


DRIVER = CARD_SHIMS + f"""
const {{ supportsKelvinFeature, sliderColor }} =
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
  colors: input.paintKelvins.map(sliderColor),
  rgbs: input.paintKelvins.map(kelvinToRgb),
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

# Bottom, middle and top of the usual range.
PAINT_KELVINS = [1000, 5500, 10000]


@pytest.fixture(scope="module")
def result():
    return _node_eval(
        DRIVER,
        {"states": STATES, "entityIds": ENTITY_IDS, "paintKelvins": PAINT_KELVINS},
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


def test_the_fill_is_the_colour_of_the_current_value(result):
    """The entire feature. The colour comes from the card's own
    kelvinToRgb, already parity-tested against curve.py, so the bar and
    the curve above it in the same section agree by construction - a
    second, drifting copy of the conversion would fail here."""
    for color, rgb in zip(result["colors"], result["rgbs"]):
        assert color == "rgb({}, {}, {})".format(*rgb)


def test_the_colour_actually_moves_with_the_value(result):
    """Guards the case the test above would still pass on: a fill painted
    from a fixed colour rather than the current value."""
    assert len(set(result["colors"])) == len(result["colors"])


# The frontend's own cardFeatureStyles rule for ha-control-slider
# (src/panels/lovelace/card-features/common/card-feature-styles.ts),
# minus the two colour properties - see PER_VALUE_PROPERTIES below.
# Note the OPACITY stays: the unfilled remainder is faded by the same
# native 0.2 the built-in uses, so only the hue is ours.
NATIVE_SLIDER_PROPERTIES = {
    "--control-slider-background-opacity": "0.2",
    "--control-slider-thickness": "var(--feature-height)",
    "--control-slider-border-radius": "var(--feature-border-radius)",
}

# The two the built-in points at --feature-color and this points at the
# colour of the value - the whole substitution, and the only reason the
# feature exists.
PER_VALUE_PROPERTIES = ["--control-slider-color", "--control-slider-background"]


def test_it_styles_the_native_slider_exactly_as_the_built_in_feature_does():
    """The point of using ha-control-slider is to look like the built-in
    slider sitting next to it in the same row, not merely similar - so
    every custom property the frontend sets on it, this sets identically.

    Asserted against the source text rather than a rendered tile: these
    are one-line declarations whose only failure mode is drifting from
    upstream, and there is no DOM in this test layer to render into."""
    source = SLIDER_JS.read_text()

    for prop, value in NATIVE_SLIDER_PROPERTIES.items():
        assert f"{prop}: {value};" in source, f"{prop} does not match cardFeatureStyles"


@pytest.mark.parametrize("prop", PER_VALUE_PROPERTIES)
def test_both_halves_of_the_bar_are_set_per_value(prop):
    """The fill and the unfilled remainder are both set from script, so
    both can take the colour of the current value - the remainder simply
    faded by the native opacity. The built-in points both at
    --feature-color, the tile's phase colour; pointing both at the value
    instead is the whole substitution."""
    assert f"setProperty('{prop}'" in SLIDER_JS.read_text(), f"{prop} is never set per value"


def test_colour_temperature_paints_both_halves_from_one_conversion():
    """Not two colour functions that could disagree - the same one, so
    the fill and the faded remainder can never be different hues."""
    source = FEATURE_JS.read_text()

    assert "fillFor: sliderColor," in source
    assert "trackFor: sliderColor," in source


def test_the_track_colour_is_never_pinned_statically():
    """The shared CSS declares neither colour property.

    The frontend's own rule points both at --feature-color, the tile's
    colour. Neither is wanted: the fill is the value's, and a feature
    with no trackFor deliberately falls through to ha-control-slider's
    own default (--disabled-color, a neutral grey) rather than being
    tinted with the tile's phase colour.

    Pinning it here would also mean a feature that sets it per value has
    it declared twice, where whichever wins depends silently on
    specificity."""
    source = SLIDER_JS.read_text()
    style_block = source[source.index("style.textContent = `") : source.index("this._slider = document")]

    # Match on the colon: a bare `--control-slider-background` is also a
    # prefix of `--control-slider-background-opacity`, which legitimately
    # IS in the static block.
    assert "--control-slider-background:" not in style_block
    assert "--control-slider-color:" not in style_block
    # The opacity is still ours - it matches cardFeatureStyles, and the
    # default happens to agree.
    assert "--control-slider-background-opacity: 0.2;" in style_block


def test_the_feature_is_registered_for_the_card_editor(result):
    """Without isSupported, Home Assistant offers the feature on every
    entity in the house; without the registration it never appears in the
    editor at all, however correct the element is."""
    feature = result["feature"]

    assert feature is not None, "not pushed to window.customCardFeatures"
    assert feature["name"] == "FLARE Colour temperature"
    assert feature["hasIsSupported"]


def test_the_colour_functions_are_given_the_config_and_hass():
    """A feature can colour itself from something other than its own
    value - brightness borrows its hue from a colour-temperature entity
    named in its config - and that only works if the factory hands both
    the config and hass through to the colour function.

    Dropping either FAILS SILENTLY: every colour function still returns
    a perfectly good colour, just always the fallback one. The features'
    own tests call those functions directly with all four arguments, so
    they cannot see it either - which is how mutation testing found this
    was unguarded."""
    source = SLIDER_JS.read_text()
    args = source[source.index("const args = [") : source.index("\n", source.index("const args = ["))]

    assert "this._config" in args, "the colour function cannot see its own config"
    assert "this._hass" in args, "the colour function cannot see hass"
