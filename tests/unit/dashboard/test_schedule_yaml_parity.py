"""The playground's copy of the schedule format, docs/assets/js/schedule-yaml.js,
must write what export_schedule writes and accept what import_schedule
accepts, so a schedule moves between the two unchanged."""

import pytest
import yaml

from custom_components.flare.schedule.curve import DEFAULT_CURVE_VALUES
from custom_components.flare.schedule.transfer import ScheduleError, dump, parse
from tests.support import REPO_ROOT
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

SCHEDULE_JS = js_path(REPO_ROOT / "docs" / "assets" / "js" / "schedule-yaml.js")

VALUE_SETS = [
    {
        **DEFAULT_CURVE_VALUES,
        "morning_time": "06:00:00",
        "day_time": "08:30:00",
        "evening_earliest_time": "17:00:00",
        "evening_latest_time": "20:00:00",
        "night_time": "22:15:30",
    },
    {"night_kelvin": 2000},
    {"evening_latest_time": "21:05:00", "day_brightness": 0},
]

# Times quoted: an unquoted one is a YAML 1.1 number to PyYAML and a string
# to js-yaml, and parse() reads the text itself, not either parser's output.
DOCUMENTS = [
    'morning:\n  time: "6:05"\n  kelvin: 6000\n',
    "day:\n  brightness: 200\n  brightness_transition: 0\n",
    'evening:\n  earliest: "16:30"\n  latest: "21:00:30"\n',
    "night:\n  brightness: 256\n",
    "night:\n  kelvin: 999\n",
    "day:\n  brightness: 12.5\n",
    'night:\n  time: "24:00"\n',
    'evening:\n  time: "18:00"\n',
    "dusk:\n  brightness: 10\n",
    "morning: 6\n",
    "- morning\n",
]


@pytest.fixture(scope="module")
def js():
    return run_js(
        f"""
const {{ scheduleYaml, scheduleValues }} = await import({SCHEDULE_JS});
const attempt = (doc) => {{
  try {{ return {{ values: scheduleValues(doc) }}; }} catch (err) {{ return {{ error: err.message }}; }}
}};
return {{
  written: input.valueSets.map(scheduleYaml),
  read: input.docs.map(attempt),
}};""",
        # What js-yaml hands the page: typed numbers, string times.
        {"valueSets": VALUE_SETS, "docs": [yaml.safe_load(d) for d in DOCUMENTS]},
    )


@pytest.mark.parametrize("index", range(len(VALUE_SETS)))
def test_the_playground_writes_exactly_what_export_writes(js, index):
    assert js["written"][index] == dump(VALUE_SETS[index])


@pytest.mark.parametrize("index", range(len(DOCUMENTS)), ids=lambda i: DOCUMENTS[i].split("\n")[0])
def test_the_playground_accepts_and_refuses_what_import_does(js, index):
    try:
        expected = {"values": parse(DOCUMENTS[index])}
    except ScheduleError:
        expected = None

    if expected is None:
        assert "error" in js["read"][index], "import refuses this, so the playground should too"
    else:
        assert js["read"][index] == expected
