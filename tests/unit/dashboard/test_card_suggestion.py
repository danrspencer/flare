"""The curve card's suggestion in HA's entity-first card picker: offered
for schedule sensors, and nothing else. And what its `sensor:` option
names."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js
from tests.support.registry import flare_entities, schedule_entities, zone_entities

# The registry says which are schedule sensors, renamed or not.
ENTITIES = {
    **schedule_entities("downstairs", "downstairs"),
    **zone_entities("downstairs_zone", "downstairs"),
    **flare_entities("garden", {"schedule": "sensor.outside"}),
    "sensor.solar_flare": {"entity_id": "sensor.solar_flare", "platform": "solar"},
    "light.kitchen": {"entity_id": "light.kitchen", "platform": "hue"},
}
NOT_SCHEDULES = [e for e in ENTITIES if e not in ("sensor.downstairs_flare", "sensor.outside")]

pytestmark = requires_node


@pytest.fixture(scope="module")
def result():
    js = run_js(
        f"""
const {{ entitySuggestion, scheduleSensorId }} = await import({js_path(WWW / "flare-curve-card.js")});
const hass = {{ entities: input }};
const entry = globalThis.customCards.find((c) => c.type === 'flare-curve-card');
return {{
  suggestions: Object.keys(input).map((id) => entitySuggestion(hass, id)),
  ids: ['ground_floor', 'sensor.outside', '  downstairs ', '', null].map(scheduleSensorId),
  card: {{
    hasSuggestion: typeof entry.getEntitySuggestion === 'function',
    preview: entry.preview,
    documentationURL: entry.documentationURL,
  }},
}};""",
        ENTITIES,
    )
    return {"suggestions": dict(zip(ENTITIES, js["suggestions"])), "ids": js["ids"], "card": js["card"]}


def test_a_schedule_sensor_is_suggested_full_width(result):
    """Full width, since a card in a sections view doesn't inherit its
    section's width."""
    assert result["suggestions"]["sensor.downstairs_flare"]["config"] == {
        "type": "custom:flare-curve-card",
        "sensor": "sensor.downstairs_flare",
        "grid_options": {"columns": "full"},
    }


def test_a_renamed_schedule_sensor_is_suggested_too(result):
    assert result["suggestions"]["sensor.outside"]["config"]["sensor"] == "sensor.outside"


@pytest.mark.parametrize("entity_id", NOT_SCHEDULES)
def test_nothing_else_is_suggested(result, entity_id):
    assert result["suggestions"][entity_id] is None


def test_sensor_takes_the_short_name_or_an_entity_id(result):
    assert result["ids"] == ["sensor.ground_floor_flare", "sensor.outside", "sensor.downstairs_flare", None, None]


def test_the_card_is_registered_with_the_picker_metadata(result):
    assert result["card"] == {
        "hasSuggestion": True,
        "preview": True,
        "documentationURL": "https://danrspencer.github.io/flare/",
    }
