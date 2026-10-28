"""The Clear control: pressing it presses Clear, or clears an area's
claimed lights."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js
from tests.support.registry import settings_entities

pytestmark = requires_node


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
await import({js_path(WWW / "flare-clear-card.js")});
const Card = defined['flare-clear-card'];
HTMLElement.prototype.attachShadow = function () {{
  const handlers = {{}};
  const name = {{ textContent: '' }};
  this.shadowRoot = {{ innerHTML: '', querySelector: (s) => (s === '.name' ? name : {{ addEventListener: (type, fn) => (handlers[type] = fn) }}) }};
  this._name = name;
  this._handlers = handlers;
  return this.shadowRoot;
}};
const card = new Card();
card.setConfig({{ entity: 'button.flare_clear' }});
const calls = [];
card.hass = {{ callService: (...args) => calls.push(args) }};
card._handlers.click();
const all = new Card();
all.setConfig({{ entity: ['button.kitchen_flare_clear', 'button.hall_flare_clear'] }});
const allCalls = [];
all.hass = {{ callService: (...args) => allCalls.push(args) }};
all._handlers.click();
const kitchen = new Card();
kitchen.setConfig({{ area: 'kitchen' }});
const areaCalls = [];
kitchen.hass = {{ ...input, callService: (...args) => areaCalls.push(args) }};
kitchen._handlers.click();
const hall = new Card();
hall.setConfig({{ area: 'hall' }});
const hallCalls = [];
hall.hass = {{ ...input, callService: (...args) => hallCalls.push(args) }};
hall._handlers.click();
let refused = null;
try {{ new Card().setConfig({{}}); }} catch (err) {{ refused = err.message; }}
let refusedEmpty = null;
try {{ new Card().setConfig({{ entity: [] }}); }} catch (err) {{ refusedEmpty = err.message; }}
return {{ calls, allCalls, areaCalls, hallCalls, html: card.shadowRoot.innerHTML, name: card._name.textContent, grid: card.getGridOptions(), refused, refusedEmpty }};
""",
        {
            "entities": {
                **settings_entities(),
                "light.k1": {"entity_id": "light.k1", "area_id": "kitchen"},
                "light.k2": {"entity_id": "light.k2", "area_id": "kitchen"},
                "light.h1": {"entity_id": "light.h1", "area_id": "hall"},
            },
            "states": {
                "sensor.flare_claims": {
                    "attributes": {
                        "rooms": {"automation.kitchen": {"lights": ["light.k1", "light.k2", "light.h1"]}},
                        "statuses": {"light.k1": "overridden", "light.k2": "controlled"},
                    }
                }
            },
        },
    )


def test_pressing_it_presses_the_clear_button(result):
    assert result["calls"] == [["button", "press", {"entity_id": "button.flare_clear"}]]


def test_for_an_area_it_clears_that_areas_claimed_lights(result):
    """Not the room's lights in other areas, nor the ones with no claim."""
    assert result["areaCalls"] == [["flare", "claims_clear", {"entities": ["light.k1", "light.k2"]}]]


def test_for_an_area_with_nothing_claimed_it_calls_nothing(result):
    assert result["hallCalls"] == []


def test_it_reads_clear_beside_its_icon(result):
    assert "mdi:backup-restore" in result["html"]
    assert result["name"] == "Clear"


def test_it_takes_a_quarter_of_the_row(result):
    assert result["grid"] == {"columns": 3, "rows": 1}


def test_it_needs_an_entity_or_an_area(result):
    assert result["refused"] == "entity or area is required"


def test_a_list_of_clear_buttons_is_pressed_together(result):
    assert result["allCalls"] == [
        ["button", "press", {"entity_id": ["button.kitchen_flare_clear", "button.hall_flare_clear"]}]
    ]


def test_an_empty_list_is_refused(result):
    assert result["refusedEmpty"] == "entity or area is required"
