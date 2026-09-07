"""
The brightness card feature.

Brightness has no colour of its own, so unlike colour temperature it
cannot be painted in "what it will look like". The value is carried by
INTENSITY instead - the theme's accent colour, faded in proportion.

Two things are worth pinning: the scaling (a fill that vanishes at the
low end looks broken rather than dim), and which entities it offers
itself for. A unit-less number is a weak signal, so an over-broad check
turns this up in the card editor for every plain number in the house.
"""

import json
import shutil

import pytest

from test_curve_js_parity import CARD_JS, CARD_SHIMS, _node_eval

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

FEATURE_JS = CARD_JS.parent / "flare-brightness-feature.js"


DRIVER = CARD_SHIMS + f"""
globalThis.customElements.whenDefined = () => Promise.resolve();
const {{ fillStrength, brightnessColor, supportsBrightnessFeature }} =
  await import({json.dumps(FEATURE_JS.as_posix())});

const input = JSON.parse(await new Promise((resolve) => {{
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => (buf += c));
  process.stdin.on('end', () => resolve(buf));
}}));

const hass = {{ states: input.states }};

process.stdout.write(JSON.stringify({{
  strengths: input.values.map((v) => fillStrength(v, {{ min: 0, max: 255 }})),
  percentStrengths: input.values.map((v) => fillStrength(v, {{ min: 0, max: 100 }})),
  colors: input.values.map((v) => brightnessColor(v, {{ min: 0, max: 255 }})),
  supported: input.entityIds.map((id) => supportsBrightnessFeature(hass, {{ entity_id: id }})),
  registered: globalThis.window.customCardFeatures.map((f) => f.type),
}}));
"""

VALUES = [0, 80, 128, 180, 255]

STATES = {
    # FLARE's own brightness values: a plain number, no unit, 0-255.
    "number.downstairs_morning_brightness": {"entity_id": "number.downstairs_morning_brightness", "attributes": {"min": 0, "max": 255}},
    # Colour temperature and transitions both carry a unit.
    "number.downstairs_morning_kelvin": {
        "attributes": {"unit_of_measurement": "K", "min": 1000, "max": 10000}
    },
    "number.downstairs_morning_brightness_transition": {
        "attributes": {"unit_of_measurement": "min", "min": 0, "max": 1440}
    },
    # A unit-less number that is not a brightness. Without the range
    # check this would be offered the feature, which is the whole reason
    # the check is not just "no unit".
    "number.some_other_thing": {"entity_id": "number.some_other_thing", "attributes": {"min": 0, "max": 10}},
    "light.kitchen": {"entity_id": "light.kitchen", "attributes": {}},
}
ENTITY_IDS = list(STATES)


@pytest.fixture(scope="module")
def result():
    return _node_eval(DRIVER, {"values": VALUES, "entityIds": ENTITY_IDS, "states": STATES})


def test_the_fill_never_fades_to_nothing(result):
    """A slider whose fill vanishes at its low end looks broken rather
    than dim. The value is carried by the fill's width too, so this only
    has to stay visible."""
    assert result["strengths"][0] == pytest.approx(0.1)


def test_the_fill_is_full_strength_at_the_top(result):
    assert result["strengths"][-1] == pytest.approx(1.0)


def test_strength_rises_with_the_value(result):
    """Guards the case every other assertion here would still pass on: a
    fixed strength that happens to hit the endpoints."""
    strengths = result["strengths"]

    assert strengths == sorted(strengths)
    assert len(set(strengths)) == len(strengths)


def test_strength_is_scaled_from_the_entitys_own_range(result):
    """Not an assumed 0-255, so the feature is still right for a
    percentage or anything else it is pointed at. 128 is roughly half of
    255 but well past the top of 0-100."""
    half_of_255 = result["strengths"][2]
    same_value_on_a_percentage = result["percentStrengths"][2]

    assert half_of_255 == pytest.approx(0.1 + 0.9 * (128 / 255), abs=1e-6)
    assert same_value_on_a_percentage == pytest.approx(1.0)


def test_the_colour_follows_the_theme_rather_than_being_hardcoded(result):
    """color-mix against --primary-color, so a user's theme applies. A
    literal blue would look wrong on every theme but the default."""
    for colour in result["colors"]:
        assert "var(--primary-color)" in colour
        assert colour.startswith("color-mix(in srgb,")


def _supported(result):
    return dict(zip(ENTITY_IDS, result["supported"]))


def test_a_flare_brightness_value_is_supported(result):
    assert _supported(result)["number.downstairs_morning_brightness"] is True


@pytest.mark.parametrize(
    "entity_id",
    [
        "number.downstairs_morning_kelvin",
        "number.downstairs_morning_brightness_transition",
        "light.kitchen",
    ],
)
def test_entities_with_a_unit_or_the_wrong_domain_are_not_supported(result, entity_id):
    assert _supported(result)[entity_id] is False


def test_a_unitless_number_of_the_wrong_range_is_not_supported(result):
    """The reason the check is not simply "a number with no unit": that
    would offer this feature for every plain number in the house."""
    assert _supported(result)["number.some_other_thing"] is False


def test_the_feature_is_registered_for_the_card_editor(result):
    assert "flare-brightness-feature" in result["registered"]
