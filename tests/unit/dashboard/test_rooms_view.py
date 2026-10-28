"""The Rooms view's layout: totals at the top, then every area holding a
room light by floor like Home Assistant's Light dashboard, with Clear where
that has "All off" and the area's live counts where that has the lights."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js
from tests.support.registry import settings_entities

pytestmark = requires_node


def _light(name):
    return {"attributes": {"friendly_name": name}}


# Upstairs has the Bedroom; Downstairs the Kitchen; the Study is on no floor.
# The Bed Lamp is placed through its device; the Hall has no room light.
CLAIMS = {
    "attributes": {
        "claims": {},
        "rooms": {
            "automation.kitchen": {"lights": ["light.k1", "light.k2", "light.k3"]},
            "automation.bedroom": {"lights": ["light.bed_lamp", "light.bed_ceiling"]},
            "automation.study": {"lights": ["light.study"]},
        },
        "statuses": {
            "light.k1": "controlled",
            "light.k2": "controlled",
            "light.k3": "overridden",
            "light.bed_lamp": "overridden",
        },
    }
}
HOUSE = {
    "states": {
        "sensor.flare_claims": CLAIMS,
        "light.bed_lamp": _light("Bed Lamp"),
        "light.bed_ceiling": _light("Bed Ceiling"),
        "light.k1": _light("Kitchen 1"),
        "light.k2": _light("Kitchen 2"),
        "light.k3": _light("Kitchen 3"),
        "light.study": _light("Study"),
    },
    "floors": {
        "upstairs": {"floor_id": "upstairs", "name": "Upstairs", "level": 1, "icon": "mdi:home-floor-1"},
        "downstairs": {"floor_id": "downstairs", "name": "Downstairs", "level": 0, "icon": None},
    },
    "areas": {
        "bedroom": {"area_id": "bedroom", "name": "Bedroom", "floor_id": "upstairs"},
        "kitchen": {"area_id": "kitchen", "name": "Kitchen", "floor_id": "downstairs"},
        "study": {"area_id": "study", "name": "Study", "floor_id": None},
        "hall": {"area_id": "hall", "name": "Hall", "floor_id": "downstairs"},
    },
    "devices": {"bed_lamp_device": {"area_id": "bedroom"}},
    "entities": {
        **settings_entities(),
        "light.bed_lamp": {"entity_id": "light.bed_lamp", "device_id": "bed_lamp_device"},
        "light.bed_ceiling": {"entity_id": "light.bed_ceiling", "area_id": "bedroom"},
        "light.k1": {"entity_id": "light.k1", "area_id": "kitchen"},
        "light.k2": {"entity_id": "light.k2", "area_id": "kitchen"},
        "light.k3": {"entity_id": "light.k3", "area_id": "kitchen"},
        "light.study": {"entity_id": "light.study", "area_id": "study"},
        "light.hall": {"entity_id": "light.hall", "area_id": "hall"},
    },
    "config": {"components": ["logbook"]},
}


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
await import({js_path(WWW / "flare-view-strategy.js")});
const {{ areaSummary }} = await import({js_path(WWW / "flare-area-card.js")});
const empty = {{ ...input, states: {{ ...input.states, 'sensor.flare_claims': {{ attributes: {{}} }} }} }};
const noSettings = {{ ...input, entities: {{}} }};
return {{
  view: await defined['ll-strategy-view-flare-rooms'].generate({{}}, input),
  oldName: await defined['ll-strategy-view-flare-zone'].generate({{}}, input),
  empty: await defined['ll-strategy-view-flare-rooms'].generate({{}}, empty),
  noSettings: await defined['ll-strategy-view-flare-rooms'].generate({{}}, noSettings),
  kitchen: areaSummary(input, 'kitchen'),
  bedroom: areaSummary(input, 'bedroom'),
  hall: areaSummary(input, 'hall'),
}};
""",
        HOUSE,
    )


@pytest.fixture(scope="module")
def view(result):
    return result["view"]


def _headings(section, style=None):
    return [c["heading"] for c in section["cards"] if c["type"] == "heading" and c.get("heading_style") == style]


def test_the_totals_come_first(view):
    totals = view["sections"][0]
    title, heading, clear = totals["cards"][:3]
    tiles = [t["entity"] for card in totals["cards"] if card["type"] == "grid" for t in card["cards"]]

    assert (title["heading"], heading["heading"]) == ("Rooms", "All rooms")
    assert "tap_action" not in heading
    assert (clear["type"], clear["entity"]) == ("custom:flare-clear-card", "button.flare_clear")
    assert set(tiles) == {"sensor.flare_controlled_lights", "sensor.flare_overridden_lights"}


@pytest.mark.parametrize(("status", "color", "first"), [("controlled", "blue", 0), ("overridden", "amber", 2)])
def test_a_total_is_coloured_only_while_it_has_lights(view, status, color, first):
    """One of each pair is shown at a time, so the counts still fill the row."""
    counts = next(c for c in view["sections"][0]["cards"] if c["type"] == "grid")
    coloured, grey = counts["cards"][first : first + 2]
    some = {"condition": "numeric_state", "entity": f"sensor.flare_{status}_lights", "above": 0}

    assert (coloured["color"], coloured["visibility"]) == (color, [some])
    assert (grey["color"], grey["visibility"]) == ("grey", [{"condition": "not", "conditions": [some]}])


def test_areas_with_room_lights_are_grouped_by_floor(view):
    """Floors by level, then areas on no floor. The Hall has lights, but none
    any automation named."""
    sections = view["sections"][1:]
    assert [s["cards"][0]["heading"] for s in sections] == ["Downstairs", "Upstairs", "Other areas"]
    assert [_headings(s, "subtitle") for s in sections] == [["Kitchen"], ["Bedroom"], ["Study"]]


def test_an_areas_row_is_clear_then_its_live_counts(view):
    downstairs = view["sections"][1]
    heading, clear, wide, narrow = downstairs["cards"][1:5]

    assert heading["tap_action"] == {"action": "navigate", "navigation_path": "/config/areas/area/kitchen"}
    assert (clear["type"], clear["area"]) == ("custom:flare-clear-card", "kitchen")
    assert (wide["type"], wide["area"]) == ("custom:flare-area-card", "kitchen")
    assert clear["grid_options"]["columns"] + wide["grid_options"]["columns"] == 12
    assert wide["visibility"] == [{"condition": "view_columns", "min": 2}]
    assert (narrow["area"], narrow["grid_options"]) == ("kitchen", {"columns": "full"})
    assert narrow["visibility"] == [{"condition": "view_columns", "max": 1}]


def test_an_areas_counts_come_from_the_claims_sensor(result):
    """A light counts in its own area, or its device's."""
    assert result["kitchen"] == {"controlled": 2, "overridden": 1, "overriddenNames": ["Kitchen 3"]}
    assert result["bedroom"] == {"controlled": 0, "overridden": 1, "overriddenNames": ["Bed Lamp"]}
    assert result["hall"] == {"controlled": 0, "overridden": 0, "overriddenNames": []}


def test_activity_follows_flares_device_in_the_sidebar(view):
    assert view["sidebar"]["sidebar_label"] == "Activity"
    activity = view["sidebar"]["sections"][0]["cards"][1]
    assert (activity["type"], activity["device_id"]) == ("custom:flare-activity-card", ["flare_device"])


def test_the_view_answers_to_its_name_from_before_2_0(result):
    """A dashboard someone took control of may name custom:flare-zone."""
    assert result["oldName"] == result["view"]


def test_with_no_rooms_yet_it_says_so(result):
    content = result["empty"]["sections"][-1]["cards"][0]["content"]
    assert content.startswith("No rooms yet.")


def test_without_the_settings_entry_it_says_so(result):
    content = result["noSettings"]["sections"][0]["cards"][1]["content"]
    assert "Settings" in content
