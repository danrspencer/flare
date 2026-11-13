"""The Kelvin card feature: which entities it's offered for, and that the
fill is the colour of the value as the chart draws it, with a little of
the theme's text colour so a near-white shows on a light card."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

STATES = {
    "number.downstairs_morning_kelvin": {"state": "10000", "attributes": {"unit_of_measurement": "K"}},
    "number.some_other_integration_temp": {"state": "3000", "attributes": {"unit_of_measurement": "K"}},
    "number.downstairs_morning_brightness": {"state": "255", "attributes": {"min": 0, "max": 255}},
    "number.downstairs_morning_kelvin_transition": {"state": "30", "attributes": {"unit_of_measurement": "min"}},
    # Right unit, wrong domain: nothing to set.
    "sensor.some_colour_temp": {"state": "4000", "attributes": {"unit_of_measurement": "K"}},
}
SUPPORTED = {"number.downstairs_morning_kelvin", "number.some_other_integration_temp"}
PAINT_KELVINS = [1000, 3200, 6667, 10000]


@pytest.fixture(scope="module")
def result():
    states = {eid: {"entity_id": eid, **s} for eid, s in STATES.items()}
    js = run_js(
        f"""
const {{ supportsKelvinFeature, sliderColor }} = await import({js_path(WWW / "flare-kelvin-feature.js")});
const {{ kelvinToRgb }} = await import({js_path(WWW / "flare-curve-card.js")});
const hass = {{ states: input.states }};
const entry = globalThis.window.customCardFeatures.find((f) => f.type === 'flare-kelvin-feature');
return {{
  supported: Object.keys(input.states).map((id) => supportsKelvinFeature(hass, {{ entity_id: id }})),
  noContext: [supportsKelvinFeature(hass, undefined), supportsKelvinFeature(hass, {{}})],
  colors: input.kelvins.map(sliderColor),
  rgbs: input.kelvins.map(kelvinToRgb),
  feature: entry && {{ name: entry.name, hasIsSupported: typeof entry.isSupported === 'function' }},
}};""",
        {"states": states, "kelvins": PAINT_KELVINS},
    )
    js["supported"] = dict(zip(STATES, js["supported"]))
    return js


@pytest.mark.parametrize("entity_id", STATES)
def test_offered_only_for_kelvin_numbers(result, entity_id):
    """Keyed on the unit, so it works for any integration's Kelvin number."""
    assert result["supported"][entity_id] is (entity_id in SUPPORTED)


def test_not_offered_without_an_entity(result):
    assert result["noContext"] == [False, False]


def test_the_fill_is_the_colour_of_the_value(result):
    for color, rgb in zip(result["colors"], result["rgbs"]):
        assert color.startswith("color-mix(in srgb, rgb({}, {}, {}) ".format(*rgb))
        assert color.endswith("%, var(--primary-text-color))")
    assert len(set(result["colors"])) == len(PAINT_KELVINS)


def text_mix(color):
    return 100 - int(color.split(") ")[1].split("%")[0])


def test_only_a_near_white_takes_much_of_the_text_colour(result):
    """A near-white needs it to show on a light card; an orange or blue already shows."""
    mixes = dict(zip(PAINT_KELVINS, map(text_mix, result["colors"])))
    assert mixes[6667] >= 12
    assert mixes[1000] == mixes[3200] == 0
    assert mixes[10000] <= 5


def test_fill_and_track_use_the_same_colour_function():
    source = (WWW / "flare-kelvin-feature.js").read_text()
    assert "fillFor: sliderColor," in source
    assert "trackFor: sliderColor," in source


def test_registered_for_the_card_editor(result):
    assert result["feature"] == {"name": "FLARE Colour temperature", "hasIsSupported": True}
