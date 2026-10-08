"""The zones' Activity: FLARE's events for the zones' devices, live from the
logbook's stream, filtered by kind, each row HA's own ha-logbook-entry with
its dot in the kind's colour."""

import time

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js
from tests.support.registry import zone_entities

pytestmark = requires_node

NOW = time.time()
DAY = 86400
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
// Just enough DOM for the card: elements are plain objects.
const element = (tag) => ({{
  tag, children: [], className: '', textContent: '', innerHTML: '',
  append(...nodes) {{ this.children.push(...nodes); }},
  replaceChildren() {{ this.children = []; }},
}});
globalThis.document = {{ createElement: element }};
const defined = {{ 'ha-logbook-entry': class {{}} }};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
globalThis.customElements.get = (name) => defined[name];
let listeners = {{}};
const parts = {{ '.chips': element('div'), '.list': element('div') }};
HTMLElement.prototype.attachShadow = function () {{
  this.shadowRoot = {{
    innerHTML: '',
    querySelector: (selector) => parts[selector],
    addEventListener: (type, fn) => (listeners[type] = fn),
  }};
  return this.shadowRoot;
}};
globalThis.history = {{ pushState: (_s, _t, url) => (navigated = url) }};
let navigated = null;
globalThis.dispatchEvent = () => {{}};

const {{ entityKinds, visibleEntries, plan, dayHeading }} = await import({js_path(WWW / "flare-activity-card.js")});
const Card = defined['flare-activity-card'];

const subscribed = [];
const hass = {{
  entities: input.entities,
  locale: {{ language: 'en-GB' }},
  localize: () => 'No logbook events found.',
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
await card._loading;
const rows = parts['.list'].children.map((c) =>
  c.tag === 'h4' ? {{ heading: c.textContent }} : {{ tag: c.tag, message: c.item.message, nodeColor: c.nodeColor, narrow: c.narrow, noIcon: c.noIcon }}
);
listeners['click']({{ composedPath: () => [{{ dataset: {{ filter: 'overridden' }} }}] }});
const overriddenOnly = parts['.list'].children.filter((c) => c.item).map((c) => c.item.message);
listeners['logbook-entry-selected']({{ stopPropagation() {{}}, detail: {{ item: input.events[1] }} }});

const kinds = entityKinds(hass, ['kitchen_zone', 'hall_zone']);
const since = Date.now() / 1000 - 24 * 3600;
const today = Date.now() / 1000;
return {{
  subscribed,
  rows,
  overriddenOnly,
  navigated,
  kinds,
  shown: visibleEntries(input.events, kinds, 'all', since).map((e) => e.message),
  cleared: visibleEntries(input.events, kinds, 'cleared', since).map((e) => e.message),
  plan: plan(
    [{{ when: today, entity_id: 'sensor.kitchen_flare_controlled' }}, {{ when: today - 60, entity_id: 'sensor.hall_flare_overridden' }}, {{ when: today - 2 * 86400, entity_id: 'button.kitchen_flare_clear' }}],
    kinds
  ).map((r) => (r.day !== undefined ? 'day' : [r.nodeColor, r.firstOfDay, r.lastOfDay])),
  headings: [dayHeading(today, 'en-GB'), dayHeading(today - 86400, 'en-GB')],
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
    assert result["overriddenOnly"] == ["released Hall Spot to something else"]


def test_each_row_is_has_own_logbook_entry_coloured_by_kind(result):
    """As the logbook card in a sidebar lays it out: narrow, with a dot."""
    heading, *entries = result["rows"]
    assert heading["heading"].startswith("Today · ")
    assert [(e["tag"], e["nodeColor"]) for e in entries] == [
        ("ha-logbook-entry", "var(--grey-color, #9e9e9e)"),
        ("ha-logbook-entry", "var(--amber-color, #ffc107)"),
        ("ha-logbook-entry", "var(--blue-color, #2196f3)"),
    ]
    assert all(e["narrow"] and e["noIcon"] for e in entries)


def test_each_day_gets_a_heading_and_trims_its_rail(result):
    """First and last of day, as ha-logbook-renderer tells its rows."""
    assert result["plan"] == [
        "day",
        ["var(--blue-color, #2196f3)", True, False],
        ["var(--amber-color, #ffc107)", False, True],
        "day",
        ["var(--grey-color, #9e9e9e)", True, True],
    ]


def test_days_are_headed_as_the_logbook_heads_them(result):
    today, yesterday = result["headings"]
    assert today.startswith("Today · ")
    assert yesterday.startswith("Yesterday · ")


def test_selecting_an_entry_opens_its_zones_device_page(result):
    assert result["navigated"] == "/config/devices/device/hall_zone"
