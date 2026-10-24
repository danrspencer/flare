"""Names and options from entities and card config reach the cards'
markup as text, never as markup."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

HOSTILE = '"><img src=x onerror=alert(1)>'
ESCAPED = "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
const {{ escapeHtml }} = await import({js_path(WWW / "flare-html.js")});
await import({js_path(WWW / "flare-curve-card.js")});
await import({js_path(WWW / "flare-clear-card.js")});
globalThis.requestAnimationFrame = () => 0;
const element = () => new Proxy(function () {{}}, {{ get: (t, k) => (k === 'style' || k === 'dataset' ? {{}} : element()), apply: () => element() }});
HTMLElement.prototype.attachShadow = function () {{
  this.shadowRoot = {{ innerHTML: '', querySelector: () => element(), querySelectorAll: () => [] }};
  return this.shadowRoot;
}};

const missing = new defined['flare-curve-card']();
missing.setConfig({{ sensor: 'sensor.' + input.hostile }});
missing.hass = {{ states: {{}} }};

const named = new defined['flare-curve-card']();
named.setConfig({{ sensor: 'home' }});
named.hass = {{ states: {{ 'sensor.home_flare': {{ state: input.hostile, attributes: {{ friendly_name: input.hostile }} }} }} }};

const titled = new defined['flare-curve-card']();
titled.setConfig({{ sensor: 'home', title: input.hostile }});
titled.hass = {{ states: {{ 'sensor.home_flare': {{ state: 'Day', attributes: {{}} }} }} }};

const clear = new defined['flare-clear-card']();
clear.setConfig({{ entity: 'button.kitchen_flare_clear', name: input.hostile }});

return {{
  missing: missing.shadowRoot.innerHTML,
  named: named.shadowRoot.innerHTML,
  titled: titled.shadowRoot.innerHTML,
  clear: clear.shadowRoot.innerHTML,
  ampersand: escapeHtml("Tom & Jerry's"),
}};
""",
        {"hostile": HOSTILE},
    )


@pytest.mark.parametrize("card", ["missing", "named", "titled", "clear"])
def test_a_hostile_name_is_shown_as_text(result, card):
    assert "<img" not in result[card]
    assert ESCAPED in result[card]


def test_ampersands_and_apostrophes_are_escaped(result):
    assert result["ampersand"] == "Tom &amp; Jerry&#39;s"
