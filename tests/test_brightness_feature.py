"""
The brightness card feature.

Brightness has no colour of its own, so it borrows one, and the fill's
width carries the value - which is what Home Assistant's own
`light-brightness` feature does with a bulb's colour.

Two things are worth pinning: that the borrowed colour really is the
tinting entity's and survives every way that entity can be missing, and
which entities the feature offers itself for. A unit-less number is a
weak signal, so an over-broad check turns this up in the card editor for
every plain number in the house.
"""

import json
import shutil

import pytest

from test_curve_js_parity import CARD_JS, CARD_SHIMS, _node_eval

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

FEATURE_JS = CARD_JS.parent / "flare-brightness-feature.js"


DRIVER = CARD_SHIMS + f"""
globalThis.customElements.whenDefined = () => Promise.resolve();
const {{ brightnessColor, supportsBrightnessFeature, tintKelvin }} =
  await import({json.dumps(FEATURE_JS.as_posix())});

const input = JSON.parse(await new Promise((resolve) => {{
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => (buf += c));
  process.stdin.on('end', () => resolve(buf));
}}));

const hass = {{ states: input.states }};

process.stdout.write(JSON.stringify({{
  untinted: brightnessColor({{}}, hass),
  warm: brightnessColor({{ tint_from: 'number.warm_kelvin' }}, hass),
  cool: brightnessColor({{ tint_from: 'number.cool_kelvin' }}, hass),
  unreadable: brightnessColor({{ tint_from: 'number.unavailable_kelvin' }}, hass),
  tintCases: [
    tintKelvin({{ tint_from: 'number.warm_kelvin' }}, hass),
    tintKelvin({{ tint_from: 'number.unavailable_kelvin' }}, hass),
    tintKelvin({{ tint_from: 'number.does_not_exist' }}, hass),
    tintKelvin({{}}, hass),
    tintKelvin(undefined, hass),
  ],
  supported: input.entityIds.map((id) => supportsBrightnessFeature(hass, {{ entity_id: id }})),
  registered: globalThis.window.customCardFeatures.map((f) => f.type),
}}));
"""

STATES = {
    # FLARE's own brightness values: a plain number, no unit, 0-255.
    "number.downstairs_morning_brightness": {
        "entity_id": "number.downstairs_morning_brightness",
        "attributes": {"min": 0, "max": 255},
    },
    # Colour temperature and transitions both carry a unit.
    "number.downstairs_morning_kelvin": {
        "entity_id": "number.downstairs_morning_kelvin",
        "attributes": {"unit_of_measurement": "K", "min": 1000, "max": 10000},
    },
    "number.downstairs_morning_brightness_transition": {
        "entity_id": "number.downstairs_morning_brightness_transition",
        "attributes": {"unit_of_measurement": "min", "min": 0, "max": 1440},
    },
    # A unit-less number that is not a brightness. Without the range
    # check this would be offered the feature, which is the whole reason
    # the check is not just "no unit".
    "number.some_other_thing": {
        "entity_id": "number.some_other_thing",
        "attributes": {"min": 0, "max": 10},
    },
    "light.kitchen": {"entity_id": "light.kitchen", "attributes": {}},
    # What a brightness slider borrows its colour from.
    "number.warm_kelvin": {
        "entity_id": "number.warm_kelvin",
        "state": "2700",
        "attributes": {"unit_of_measurement": "K", "min": 1000, "max": 10000},
    },
    "number.cool_kelvin": {
        "entity_id": "number.cool_kelvin",
        "state": "10000",
        "attributes": {"unit_of_measurement": "K", "min": 1000, "max": 10000},
    },
    "number.unavailable_kelvin": {
        "entity_id": "number.unavailable_kelvin",
        "state": "unavailable",
        "attributes": {"unit_of_measurement": "K", "min": 1000, "max": 10000},
    },
}
ENTITY_IDS = list(STATES)


@pytest.fixture(scope="module")
def result():
    return _node_eval(DRIVER, {"entityIds": ENTITY_IDS, "states": STATES})


# --- The borrowed colour ----------------------------------------------


def test_the_fill_is_the_colour_of_the_tinting_entity(result):
    """2700K and 10000K are FLARE's own warm and cold ends, and they must
    come out as those colours - not as some fixed accent."""
    assert result["warm"] == "rgb(255, 167, 87)"
    assert result["cool"] == "rgb(202, 218, 255)"


def test_the_fill_is_solid(result):
    """No alpha. An earlier version faded it by the value as well, which
    said the same thing the fill's width already says and only made a dim
    setting harder to see. Home Assistant's own light-brightness feature
    is a solid slider in the bulb's colour."""
    for key in ("warm", "cool"):
        assert result[key].startswith("rgb("), result[key]
        assert "rgba" not in result[key]


@pytest.mark.parametrize("index", [1, 2, 3, 4])
def test_every_way_the_tint_can_be_missing_reads_the_same(result, index):
    """Unavailable, non-existent, unset, and no config at all: they all
    want the theme colour rather than something arbitrary, so they all
    resolve to null rather than each needing their own handling."""
    assert result["tintCases"][index] is None


def test_a_readable_tint_resolves_to_its_kelvin(result):
    assert result["tintCases"][0] == 2700


@pytest.mark.parametrize("key", ["untinted", "unreadable"])
def test_without_a_usable_tint_it_is_exactly_the_stock_slider(result, key):
    """--primary-color is ha-control-slider's own default fill, so a
    feature with nothing to borrow from degrades to the stock slider
    rather than to something odd - and a colour-temp entity going
    unavailable does not blank it."""
    assert result[key] == "var(--primary-color)"


# --- Which entities it is offered for ---------------------------------


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
