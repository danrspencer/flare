"""Names and options from entities and card config reach the cards as
text and attribute values, never as markup."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

HOSTILE = '"><img src=x onerror=alert(1)>'


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
await import({js_path(WWW / "flare-curve-card.js")});

// An element per selector, found only if the markup has it, recording
// what the card sets on it.
const element = () => {{
  const el = {{ attrs: {{}}, textContent: '', style: {{}}, dataset: {{}}, clientWidth: 0 }};
  el.setAttribute = (name, value) => {{ el.attrs[name] = String(value); }};
  el.addEventListener = () => {{}};
  el.getBoundingClientRect = () => ({{ left: 0, width: 0 }});
  return el;
}};
HTMLElement.prototype.attachShadow = function () {{
  const found = {{}};
  const root = {{
    innerHTML: '',
    found,
    querySelector(selector) {{
      const marker = selector.startsWith('.') ? `class="${{selector.slice(1)}}"` : `<${{selector.split('.')[0]}}`;
      if (!root.innerHTML.includes(marker)) return null;
      return (found[selector] ||= element());
    }},
    querySelectorAll: () => [],
  }};
  this.shadowRoot = root;
  return root;
}};
const seen = (card) => ({{
  html: card.shadowRoot.innerHTML,
  header: card.shadowRoot.found['ha-card']?.attrs.header,
  error: card.shadowRoot.found['.error']?.textContent,
  phase: card.shadowRoot.found['.phase']?.textContent,
}});

const missing = new defined['flare-curve-card']();
missing.setConfig({{ sensor: 'sensor.' + input.hostile }});
missing.hass = {{ states: {{}} }};

const named = new defined['flare-curve-card']();
named.setConfig({{ sensor: 'home' }});
named.hass = {{ states: {{ 'sensor.home_flare': {{ state: input.hostile, attributes: {{ friendly_name: input.hostile }} }} }} }};

const titled = new defined['flare-curve-card']();
titled.setConfig({{ sensor: 'home', title: input.hostile }});
titled.hass = {{ states: {{ 'sensor.home_flare': {{ state: 'Day', attributes: {{}} }} }} }};

return {{ missing: seen(missing), named: seen(named), titled: seen(titled) }};
""",
        {"hostile": HOSTILE},
    )


@pytest.mark.parametrize("card", ["missing", "named", "titled"])
def test_nothing_from_a_name_reaches_the_markup(result, card):
    assert "<img" not in result[card]["html"]


def test_the_missing_entity_message_is_text(result):
    assert result["missing"]["error"] == f"Missing entity: sensor.{HOSTILE}"


def test_the_schedules_name_is_the_header_and_its_phase_is_text(result):
    assert result["named"]["header"] == HOSTILE
    assert result["named"]["phase"] == HOSTILE


def test_the_title_option_is_the_header(result):
    assert result["titled"]["header"] == HOSTILE
