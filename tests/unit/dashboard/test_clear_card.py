"""The zone's Clear control: pressing it presses the zone's Clear button."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

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
  this.shadowRoot = {{ innerHTML: '', querySelector: () => ({{ addEventListener: (type, fn) => (handlers[type] = fn) }}) }};
  this._handlers = handlers;
  return this.shadowRoot;
}};
const card = new Card();
card.setConfig({{ entity: 'button.kitchen_flare_clear' }});
const calls = [];
card.hass = {{ callService: (...args) => calls.push(args) }};
card._handlers.click();
let refused = null;
try {{ new Card().setConfig({{}}); }} catch (err) {{ refused = err.message; }}
return {{ calls, html: card.shadowRoot.innerHTML, grid: card.getGridOptions(), refused }};
""",
    )


def test_pressing_it_presses_the_zones_clear_button(result):
    assert result["calls"] == [["button", "press", {"entity_id": "button.kitchen_flare_clear"}]]


def test_it_reads_clear_beside_its_icon(result):
    assert "mdi:backup-restore" in result["html"]
    assert ">Clear<" in result["html"]


def test_it_takes_a_third_of_the_row(result):
    assert result["grid"] == {"columns": 4, "rows": 1}


def test_it_needs_an_entity(result):
    assert result["refused"] == "entity is required"
