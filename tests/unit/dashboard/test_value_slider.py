"""flare-value-slider.js, shared by both card features. Checked against
the source, since there's no DOM here to render into."""

import pytest

from tests.support import WWW

SOURCE = (WWW / "flare-value-slider.js").read_text()
STYLE_BLOCK = SOURCE[SOURCE.index("style.textContent = `") : SOURCE.index("this._slider = document")]

# The frontend's cardFeatureStyles rule for ha-control-slider, minus its
# two colour properties.
NATIVE_SLIDER_PROPERTIES = {
    "--control-slider-background-opacity": "0.2",
    "--control-slider-thickness": "var(--feature-height)",
    "--control-slider-border-radius": "var(--feature-border-radius)",
}


@pytest.mark.parametrize("prop", NATIVE_SLIDER_PROPERTIES)
def test_the_slider_is_styled_like_the_built_in_feature(prop):
    assert f"{prop}: {NATIVE_SLIDER_PROPERTIES[prop]};" in STYLE_BLOCK


@pytest.mark.parametrize("prop", ["--control-slider-color", "--control-slider-background"])
def test_colours_are_set_per_value_never_statically(prop):
    assert f"setProperty('{prop}'" in SOURCE
    assert f"{prop}:" not in STYLE_BLOCK


def test_the_colour_functions_receive_config_and_hass():
    """Brightness takes its colour from an entity named in its config;
    without these it silently falls back."""
    args = SOURCE[SOURCE.index("const args = [") :].split("\n", 1)[0]
    assert "this._config" in args
    assert "this._hass" in args
