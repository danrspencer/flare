"""The zones' Activity asks the logbook by device, as a zone's own page does."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const defined = {{}};
const loaded = new Set();
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
globalThis.customElements.get = (name) => (loaded.has(name) ? {{}} : defined[name]);
const created = [];
globalThis.loadCardHelpers = async () => ({{
  createCardElement: (config) => {{ created.push(config); loaded.add('ha-logbook'); }},
}});
const appended = [];
HTMLElement.prototype.attachShadow = function () {{
  this.shadowRoot = {{ innerHTML: '', querySelector: () => ({{ appendChild: (el) => appended.push(el) }}) }};
  return this.shadowRoot;
}};
globalThis.document = {{ createElement: (tag) => ({{ tag }}) }};

await import({js_path(WWW / "flare-activity-card.js")});
const Card = defined['flare-activity-card'];

const hass = {{
  entities: {{
    'sensor.kitchen_flare_controlled': {{ entity_id: 'sensor.kitchen_flare_controlled', device_id: 'kitchen_zone' }},
    'button.kitchen_flare_clear': {{ entity_id: 'button.kitchen_flare_clear', device_id: 'kitchen_zone' }},
    'sensor.hall_flare_controlled': {{ entity_id: 'sensor.hall_flare_controlled', device_id: 'hall_zone' }},
    'light.kitchen_1': {{ entity_id: 'light.kitchen_1', device_id: 'kitchen_bulb' }},
  }},
}};
const card = new Card();
card.setConfig({{ device_id: ['kitchen_zone', 'hall_zone'], hours_to_show: 12 }});
card.hass = hass;
await card._loading;
const logbook = appended[0];
const first = {{ entityIds: logbook.entityIds, deviceIds: logbook.deviceIds }};
card.hass = {{ ...hass }};

let refused = null;
try {{ new Card().setConfig({{ device_id: [] }}); }} catch (err) {{ refused = err.message; }}
return {{
  created,
  logbook,
  sameArraysOnRefresh: first.entityIds === logbook.entityIds && first.deviceIds === logbook.deviceIds,
  refused,
}};
""",
    )


def test_it_asks_by_the_zones_devices_and_their_entities(result):
    logbook = result["logbook"]
    assert logbook["tag"] == "ha-logbook"
    assert logbook["deviceIds"] == ["kitchen_zone", "hall_zone"]
    assert logbook["entityIds"] == [
        "button.kitchen_flare_clear",
        "sensor.hall_flare_controlled",
        "sensor.kitchen_flare_controlled",
    ]


def test_it_shows_the_hours_asked_for(result):
    assert result["logbook"]["time"] == {"recent": 12 * 60 * 60}


def test_it_loads_the_logbook_through_the_built_in_card(result):
    assert [c["type"] for c in result["created"]] == ["logbook"]


def test_a_state_update_does_not_resubscribe(result):
    assert result["sameArraysOnRefresh"]


def test_it_needs_devices(result):
    assert result["refused"] == "device_id is required"
