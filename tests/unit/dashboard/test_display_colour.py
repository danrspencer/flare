"""Kelvin colours on the sliders: pale ones are pulled away from the
card's background so they stay visible."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

KELVINS = list(range(1000, 10001, 250))
WHITE = [255, 255, 255]
DARK = [28, 28, 28]


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const m = await import({js_path(WWW / "flare-slider-colour.js")});
const {{ kelvinToRgb }} = await import({js_path(WWW / "flare-curve-card.js")});
const shown = (bg) => input.kelvins.map((k) => {{
  const raw = kelvinToRgb(k);
  const out = m.displayRgb(raw, bg);
  return {{ raw, out, before: m.contrastRatio(raw, bg), after: m.contrastRatio(out, bg) }};
}});
return {{
  min: m.MIN_CARD_CONTRAST,
  white: shown(input.white),
  dark: shown(input.dark),
  defaultIsWhite: m.displayRgb(kelvinToRgb(6500)),
  onWhite: m.displayRgb(kelvinToRgb(6500), input.white),
  css: m.kelvinCss(6500, input.white),
  noDom: m.cardBackgroundRgb(null),
}};""",
        {"kelvins": KELVINS, "white": WHITE, "dark": DARK},
    )


@pytest.mark.parametrize("theme", ["white", "dark"])
def test_every_kelvin_reaches_the_minimum_contrast(result, theme):
    # Rounding back to 8 bits can land a hair under.
    assert all(c["after"] >= result["min"] - 0.01 for c in result[theme])


@pytest.mark.parametrize("theme", ["white", "dark"])
def test_a_colour_with_enough_contrast_is_left_alone(result, theme):
    for c in result[theme]:
        if c["before"] >= result["min"]:
            assert c["out"] == c["raw"]


def test_only_the_pale_end_changes_on_a_white_card(result):
    changed = [k for k, c in zip(KELVINS, result["white"]) if c["out"] != c["raw"]]
    assert changed and min(changed) > 3200


def test_darkening_keeps_the_hue(result):
    """Channels keep their order, so a cool white stays bluish. Channels a
    rounding step apart may land equal."""
    for c in result["white"]:
        raw, out = c["raw"], c["out"]
        for i in range(3):
            for j in range(3):
                if raw[i] - raw[j] >= 3:
                    assert out[i] >= out[j]


def test_a_dark_card_needs_no_adjustment(result):
    assert all(c["out"] == c["raw"] for c in result["dark"])


def test_kelvin_css_is_the_adjusted_colour(result):
    assert result["css"] == "rgb({}, {}, {})".format(*result["onWhite"])


def test_without_a_page_the_card_is_taken_as_white(result):
    assert result["noDom"] == WHITE
    assert result["defaultIsWhite"] == result["onWhite"]
