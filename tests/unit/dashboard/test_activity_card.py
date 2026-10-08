"""The zones' Activity: FLARE's events for the zones' devices, live from the
logbook's stream, coloured and filtered by kind."""

import time

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js
from tests.support.registry import zone_entities

pytestmark = requires_node

NOW = time.time()
ENTITIES = {**zone_entities("kitchen_zone", "kitchen"), **zone_entities("hall_zone", "hall")}
EVENTS = [
    {"when": NOW - 600, "name": "Kitchen", "message": "now controlling 6 lights", "entity_id": "sensor.kitchen_flare_controlled"},
    {"when": NOW - 300, "name": "Hall", "message": "released Hall Spot to something else", "entity_id": "sensor.hall_flare_overridden"},
    {"when": NOW - 200, "name": "Kitchen", "message": "cleared 6 lights", "entity_id": "button.kitchen_flare_clear"},
    # The Clear press itself, as the button's state change: no message.
    {"when": NOW - 200, "state": "2026-10-08T10:00:00", "entity_id": "button.kitchen_flare_clear"},
    # Before the window.
    {"when": NOW - 90000, "name": "Hall", "message": "now controlling 2 lights", "entity_id": "sensor.hall_flare_controlled"},
    # Someone else's device.
    {"when": NOW - 100, "name": "Lamp", "message": "turned on", "entity_id": "light.lamp"},
]


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
const {{ entityKinds, visibleEntries }} = await import({js_path(WWW / "flare-activity-card.js")});
const Card = defined['flare-activity-card'];

let listener = null;
HTMLElement.prototype.attachShadow = function () {{
  this.shadowRoot = {{ innerHTML: '', addEventListener: (type, fn) => (listener = fn) }};
  return this.shadowRoot;
}};
const subscribed = [];
const hass = {{
  entities: input.entities,
  locale: {{ language: 'en-GB' }},
  connection: {{
    subscribeMessage: (callback, message) => {{
      subscribed.push(message);
      callback({{ events: input.events, start_time: 0, end_time: 0 }});
      return Promise.resolve(() => {{}});
    }},
  }},
}};
const card = new Card();
card.setConfig({{ device_id: ['kitchen_zone', 'hall_zone'] }});
card.hass = hass;
const all = card.shadowRoot.innerHTML;
const click = (filter) => listener({{ composedPath: () => [{{ dataset: {{ filter }} }}] }});
click('overridden');
const overriddenOnly = card.shadowRoot.innerHTML;
click('all');

const kinds = entityKinds(hass, ['kitchen_zone', 'hall_zone']);
const since = Date.now() / 1000 - 24 * 3600;
return {{
  subscribed,
  all,
  overriddenOnly,
  kinds,
  shown: visibleEntries(input.events, kinds, 'all', since).map((e) => e.message),
  cleared: visibleEntries(input.events, kinds, 'cleared', since).map((e) => e.message),
}};
""",
        {"entities": ENTITIES, "events": EVENTS},
    )


def test_it_follows_the_zones_devices_on_the_logbook_stream(result):
    (message,) = result["subscribed"]
    assert message["type"] == "logbook/event_stream"
    assert message["device_ids"] == ["kitchen_zone", "hall_zone"]


def test_an_events_kind_is_the_zone_entity_it_is_filed_under(result):
    assert result["kinds"]["sensor.kitchen_flare_controlled"] == {"kind": "controlled", "device": "kitchen_zone"}
    assert result["kinds"]["sensor.hall_flare_overridden"] == {"kind": "overridden", "device": "hall_zone"}
    assert result["kinds"]["button.kitchen_flare_clear"] == {"kind": "cleared", "device": "kitchen_zone"}


def test_only_flares_events_in_the_window_are_shown_newest_first(result):
    """Not the Clear press's own state change, nor another device's entries."""
    assert result["shown"] == ["cleared 6 lights", "released Hall Spot to something else", "now controlling 6 lights"]


def test_a_kind_can_be_shown_on_its_own(result):
    assert result["cleared"] == ["cleared 6 lights"]
    assert "released Hall Spot" in result["overriddenOnly"]
    assert "now controlling" not in result["overriddenOnly"]


def test_each_kind_has_its_own_colour(result):
    html = result["all"]
    assert "background:var(--amber-color, #ffc107)" in html
    assert "background:var(--blue-color, #2196f3)" in html
    assert "background:var(--grey-color, #9e9e9e)" in html


def test_an_entry_links_to_its_zones_device_page(result):
    assert 'data-device="hall_zone"' in result["all"]
