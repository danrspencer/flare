"""The brightness card feature: its fill borrows the colour of a
colour-temperature entity (`tint_from`), and it's offered only for
brightness numbers."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

KELVIN = {"unit_of_measurement": "K", "min": 1000, "max": 10000}
STATES = {
    "number.downstairs_morning_brightness": {"attributes": {"min": 0, "max": 255}},
    "number.downstairs_morning_kelvin": {"attributes": KELVIN},
    "number.downstairs_morning_brightness_transition": {"attributes": {"unit_of_measurement": "min", "min": 0, "max": 1440}},
    # Unit-less, but not a brightness range.
    "number.some_other_thing": {"attributes": {"min": 0, "max": 10}},
    "light.kitchen": {"attributes": {}},
    "number.warm_kelvin": {"state": "2700", "attributes": KELVIN},
    "number.cool_kelvin": {"state": "10000", "attributes": KELVIN},
    "number.unavailable_kelvin": {"state": "unavailable", "attributes": KELVIN},
}


@pytest.fixture(scope="module")
def result():
    states = {eid: {"entity_id": eid, **s} for eid, s in STATES.items()}
    return run_js(
        f"""
const {{ brightnessColor, supportsBrightnessFeature, tintKelvin }} = await import({js_path(WWW / "flare-brightness-feature.js")});
const hass = {{ states: input }};
const tint = (id) => (id === undefined ? {{}} : {{ tint_from: id }});
return {{
  color: Object.fromEntries(['number.warm_kelvin', 'number.cool_kelvin', 'number.unavailable_kelvin', undefined]
    .map((id) => [String(id), brightnessColor(tint(id), hass)])),
  tint: Object.fromEntries(['number.warm_kelvin', 'number.unavailable_kelvin', 'number.does_not_exist', undefined]
    .map((id) => [String(id), tintKelvin(tint(id), hass)])),
  tintWithoutConfig: tintKelvin(undefined, hass),
  supported: Object.fromEntries(Object.keys(input).map((id) => [id, supportsBrightnessFeature(hass, {{ entity_id: id }})])),
  registered: globalThis.window.customCardFeatures.map((f) => f.type),
}};""",
        states,
    )


def test_the_fill_is_the_tinting_entitys_colour_solid(result):
    assert result["color"]["number.warm_kelvin"] == "rgb(255, 167, 87)"
    assert result["color"]["number.cool_kelvin"] == "rgb(202, 218, 255)"


@pytest.mark.parametrize("tint", ["number.unavailable_kelvin", "undefined"])
def test_without_a_readable_tint_it_is_the_stock_slider_colour(result, tint):
    assert result["color"][tint] == "var(--primary-color)"


def test_tint_resolves_to_the_kelvin_or_null(result):
    assert result["tint"] == {
        "number.warm_kelvin": 2700,
        "number.unavailable_kelvin": None,
        "number.does_not_exist": None,
        "undefined": None,
    }
    assert result["tintWithoutConfig"] is None


@pytest.mark.parametrize("entity_id", [e for e in STATES if not e.startswith("number.warm") and not e.startswith("number.cool") and "unavailable" not in e])
def test_offered_only_for_brightness_numbers(result, entity_id):
    assert result["supported"][entity_id] is (entity_id == "number.downstairs_morning_brightness")


def test_registered_for_the_card_editor(result):
    assert "flare-brightness-feature" in result["registered"]
