"""The Schedule Transfer card: which device it names, what it asks the
services for, and copying without the Clipboard API."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

CARD = js_path(WWW / "flare-schedule-transfer-card.js")


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const card = await import({CARD});
const calls = [];
const hass = {{
  entities: {{ 'sensor.downstairs_flare': {{ device_id: 'dev-1' }} }},
  callService: async (...args) => {{
    calls.push(args);
    return {{ response: {{ schedule: 'morning:\\n  brightness: 255\\n' }} }};
  }},
}};
const exported = await card.exportSchedule(hass, 'dev-1');
await card.importSchedule(hass, 'dev-1', 'night:\\n  kelvin: 2000\\n');

// No Clipboard API, as over plain HTTP: falls back to execCommand.
const appended = [];
globalThis.document = {{
  createElement: () => ({{ style: {{}}, setAttribute() {{}}, select() {{}} }}),
  execCommand: (cmd) => cmd === 'copy',
}};
const root = {{ appendChild: (el) => appended.push(el), removeChild() {{}} }};
const copied = await card.copyText('the schedule', root);
globalThis.document.execCommand = () => false;
const notCopied = await card.copyText('the schedule', root);

return {{
  deviceId: card.scheduleDeviceId(hass, 'downstairs'),
  unknown: card.scheduleDeviceId(hass, 'attic'),
  exported,
  calls,
  copied,
  notCopied,
  copiedText: appended[0].value,
  registered: globalThis.window.customCards.map((c) => c.type),
}};""",
    )


def test_the_schedule_is_found_through_its_sensors_device(result):
    assert result["deviceId"] == "dev-1"
    assert result["unknown"] is None


def test_export_asks_for_the_response_and_returns_its_text(result):
    domain, service, data, _target, notify, return_response = result["calls"][0]
    assert (domain, service, data) == ("flare", "export_schedule", {"schedule_device_id": "dev-1"})
    assert (notify, return_response) == (False, True)
    assert result["exported"] == "morning:\n  brightness: 255\n"


def test_import_sends_the_pasted_text_as_it_is(result):
    domain, service, data, _target, notify = result["calls"][1]
    assert (domain, service) == ("flare", "import_schedule")
    assert data == {"schedule_device_id": "dev-1", "schedule": "night:\n  kelvin: 2000\n"}
    assert notify is False, "errors show in the card, not as a toast"


def test_copying_works_without_the_clipboard_api(result):
    assert result["copied"] is True
    assert result["copiedText"] == "the schedule"


def test_a_copy_that_fails_says_so(result):
    """The card then shows the text to select by hand."""
    assert result["notCopied"] is False


def test_the_card_is_offered_in_the_card_picker(result):
    assert "flare-schedule-transfer-card" in result["registered"]
