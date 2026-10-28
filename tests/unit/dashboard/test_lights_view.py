"""The Lights view's layout: totals at the top, then every area holding a
room light by floor like Home Assistant's Light dashboard, each with its
lights under its counts and Clear all."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js
from tests.support.registry import settings_entities

pytestmark = requires_node


def _light(name, state="on", **attributes):
    return {"state": state, "attributes": {"friendly_name": name, **attributes}}


KITCHEN = ["automation.kitchen"]
ASKED = {"brightness": 200, "color_temp_kelvin": 3000}


def _status(light, status, *, rooms, claimed=True, asked=None):
    """A light's status sensor: its state, and what it says of its light."""
    return {"state": status, "attributes": {"light": light, "rooms": rooms, "claimed": claimed, "asked": asked}}


# Upstairs has the Bedroom; Downstairs the Kitchen; the Study is on no floor.
# The Bed Lamp is placed through its device; the Hall has no room light.
STATUSES = {
    "k1": _status("light.k1", "controlled", rooms=KITCHEN, asked=ASKED),
    "k2": _status("light.k2", "mismatched", rooms=KITCHEN, asked={"state": "off"}),
    "k3": _status("light.k3", "overridden", rooms=KITCHEN, asked=ASKED),
    # In a dark room: FLARE's, but not a light FLARE is setting.
    "k5": _status("light.k5", "controlled", rooms=KITCHEN, asked={"state": "off"}),
    # Its room let it go, so it isn't a room light any more.
    "k4": _status("light.k4", "untracked", rooms=[], claimed=False),
    # Marked as someone else's: claimed, but nothing asked.
    "bed_lamp": _status("light.bed_lamp", "overridden", rooms=["automation.bedroom"]),
    "bed_ceiling": _status("light.bed_ceiling", "untracked", rooms=["automation.bedroom"], claimed=False),
    "study": _status("light.study", "untracked", rooms=["automation.study"], claimed=False),
}
HOUSE = {
    "states": {
        "light.bed_lamp": _light("Bed Lamp"),
        "light.bed_ceiling": _light("Bed Ceiling"),
        "light.k1": _light("Kitchen 1", brightness=200, color_temp_kelvin=3000),
        "light.k2": _light("Kitchen 2", "off"),
        "light.k3": _light("Kitchen 3", brightness=51, rgb_color=[255, 0, 0]),
        "light.k4": _light("Kitchen 4"),
        "light.k5": _light("Kitchen 5", "off"),
        "light.study": _light("Study"),
        **{f"sensor.{light}_flare_status": state for light, state in STATUSES.items()},
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
        "light.k4": {"entity_id": "light.k4", "area_id": "kitchen"},
        "light.k5": {"entity_id": "light.k5", "area_id": "kitchen"},
        **{
            f"sensor.{light}_flare_status": {
                "entity_id": f"sensor.{light}_flare_status", "platform": "flare", "translation_key": "status"
            }
            for light in STATUSES
        },
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
const {{ areaSummary, areaLights, claimedIn, describe, detail }} = await import({js_path(WWW / "flare-area-lights-card.js")});
const empty = {{ ...input, entities: Object.fromEntries(Object.entries(input.entities).filter(([, e]) => e.translation_key !== 'status')) }};
const noSettings = {{ ...input, entities: {{}} }};
return {{
  view: await defined['ll-strategy-view-flare-lights'].generate({{}}, input),
  oldName: await defined['ll-strategy-view-flare-zone'].generate({{}}, input),
  empty: await defined['ll-strategy-view-flare-lights'].generate({{}}, empty),
  noSettings: await defined['ll-strategy-view-flare-lights'].generate({{}}, noSettings),
  kitchen: areaSummary(input, 'kitchen'),
  bedroom: areaSummary(input, 'bedroom'),
  hall: areaSummary(input, 'hall'),
  kitchenLights: areaLights(input, 'kitchen'),
  bedroomLights: areaLights(input, 'bedroom'),
  described: [
    describe({{ brightness: 255, color_temp_kelvin: 2700 }}),
    describe({{ brightness: 128, rgb_color: [255, 0, 10] }}),
    describe({{ state: 'off' }}),
    describe(null),
  ],
  details: areaLights(input, 'kitchen').map(detail),
  clearAll: {{ kitchen: claimedIn(areaLights(input, 'kitchen')), bedroom: claimedIn(areaLights(input, 'bedroom')) }},
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

    assert (title["heading"], heading["heading"]) == ("Lights", "All lights")
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


def test_an_areas_row_is_its_heading_then_its_lights(view):
    downstairs = view["sections"][1]
    heading, lights = downstairs["cards"][1:]

    assert heading["tap_action"] == {"action": "navigate", "navigation_path": "/config/areas/area/kitchen"}
    assert (lights["type"], lights["area"], lights["grid_options"]) == (
        "custom:flare-area-lights-card",
        "kitchen",
        {"columns": "full"},
    )


def test_an_areas_counts_agree_with_its_lights(result):
    """A light counts in its own area, or its device's, by the status its list
    shows: Kitchen 2 is mismatched, so it's in neither, and Kitchen 5 is off,
    so FLARE isn't setting it."""
    assert result["kitchen"] == {"controlled": 1, "overridden": 1}
    assert result["bedroom"] == {"controlled": 0, "overridden": 1}
    assert result["hall"] == {"controlled": 0, "overridden": 0}


def test_an_areas_lights_are_listed_overridden_first(result):
    """From each light's status sensor. Kitchen 4's room let it go, so it
    isn't listed."""
    assert [(light["name"], light["status"], light["claimed"]) for light in result["kitchenLights"]] == [
        ("Kitchen 3", "overridden", True),
        ("Kitchen 2", "mismatched", True),
        ("Kitchen 1", "controlled", True),
        ("Kitchen 5", "controlled", True),
    ]
    assert [(light["name"], light["status"], light["claimed"]) for light in result["bedroomLights"]] == [
        ("Bed Lamp", "overridden", True),
        ("Bed Ceiling", "untracked", False),
    ]


def test_each_light_says_what_flare_asked_for_and_what_it_shows(result):
    assert result["details"] == [
        "Asked 78% · 3000K, showing 20% · RGB 255, 0, 0",
        "Asked off, showing off",
        "Asked 78% · 3000K, showing 78% · 3000K",
        "Asked off, showing off",
    ]


def test_a_light_marked_as_someone_elses_has_nothing_asked(result):
    lamp = next(light for light in result["bedroomLights"] if light["name"] == "Bed Lamp")
    assert lamp["asked"] is None


def test_clear_all_clears_the_areas_claimed_lights(result):
    """Not the Bed Ceiling, which FLARE holds nothing on."""
    assert sorted(result["clearAll"]["kitchen"]) == ["light.k1", "light.k2", "light.k3", "light.k5"]
    assert result["clearAll"]["bedroom"] == ["light.bed_lamp"]


def test_values_read_as_brightness_then_colour(result):
    assert result["described"] == ["100% · 2700K", "50% · RGB 255, 0, 10", "off", None]


def test_activity_follows_flares_device_in_the_sidebar(view):
    assert view["sidebar"]["sidebar_label"] == "Activity"
    activity = view["sidebar"]["sections"][0]["cards"][1]
    assert (activity["type"], activity["device_id"]) == ("custom:flare-activity-card", ["flare_device"])


def test_the_view_answers_to_its_name_from_before_2_0(result):
    """A dashboard someone took control of may name custom:flare-zone."""
    assert result["oldName"] == result["view"]


def test_with_no_lights_yet_it_says_so(result):
    content = result["empty"]["sections"][-1]["cards"][0]["content"]
    assert content.startswith("No lights yet.")


def test_without_the_settings_entry_it_says_so(result):
    content = result["noSettings"]["sections"][0]["cards"][1]["content"]
    assert "Settings" in content
