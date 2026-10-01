"""The curve card's suggestion in HA's entity-first card picker: offered
for schedule sensors, and nothing else."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

# A schedule sensor is identified by its `points` attribute plus the exact
# `_flare` suffix.
SCHEDULE = {"attributes": {"points": [], "phase": "Evening"}}
PLAIN = {"attributes": {}}

STATES = {
    "sensor.downstairs_flare": SCHEDULE,
    "sensor.ground_floor_flare": SCHEDULE,
    "sensor.downstairs_flare_claims": PLAIN,
    "sensor.downstairs_flare_controlled": PLAIN,
    "sensor.downstairs_flare_overridden": PLAIN,
    "select.downstairs_flare_phase": PLAIN,
    "number.downstairs_morning_brightness": PLAIN,
    "time.downstairs_morning_time": PLAIN,
    "switch.downstairs_sticky_phase_override": PLAIN,
    "button.downstairs_flare_clear": PLAIN,
    "sensor.solar_flare": PLAIN,  # someone else's, same suffix
    "light.kitchen": PLAIN,
    # Contrived: claims-shaped but carrying `points`. The only case that
    # tests the suffix check independently of the attribute check.
    "sensor.upstairs_flare_claims": SCHEDULE,
}


@pytest.fixture(scope="module")
def result():
    js = run_js(
        f"""
const {{ entitySuggestion, scheduleSensorSlug }} = await import({js_path(WWW / "flare-curve-card.js")});
const hass = {{ states: input }};
const entry = globalThis.customCards.find((c) => c.type === 'flare-curve-card');
return {{
  suggestions: Object.keys(input).map((id) => entitySuggestion(hass, id)),
  slugs: Object.keys(input).map((id) => scheduleSensorSlug(hass, id)),
  card: {{
    hasSuggestion: typeof entry.getEntitySuggestion === 'function',
    preview: entry.preview,
    documentationURL: entry.documentationURL,
  }},
}};""",
        STATES,
    )
    return {
        "suggestions": dict(zip(STATES, js["suggestions"])),
        "slugs": dict(zip(STATES, js["slugs"])),
        "card": js["card"],
    }


def test_a_schedule_sensor_is_suggested_full_width_with_the_sensor_shorthand(result):
    """Full width, since a card in a sections view doesn't inherit its
    section's width."""
    assert result["suggestions"]["sensor.downstairs_flare"]["config"] == {
        "type": "custom:flare-curve-card",
        "sensor": "downstairs",
        "grid_options": {"columns": "full"},
    }


def test_a_multi_word_slug_survives(result):
    assert result["slugs"]["sensor.ground_floor_flare"] == "ground_floor"


@pytest.mark.parametrize("entity_id", [e for e in STATES if STATES[e] is PLAIN] + ["sensor.upstairs_flare_claims"])
def test_nothing_else_is_suggested(result, entity_id):
    assert result["suggestions"][entity_id] is None
    assert result["slugs"][entity_id] is None


def test_the_card_is_registered_with_the_picker_metadata(result):
    assert result["card"] == {
        "hasSuggestion": True,
        "preview": True,
        "documentationURL": "https://danrspencer.github.io/flare/",
    }
