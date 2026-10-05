"""The Zones view's layout: totals at the top, then every zone by floor and
area like Home Assistant's Light dashboard, with Clear where that has "All
off" and the zone's two counts where that has the lights."""

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node


def _claims(friendly, claims=None):
    return {"attributes": {"claims": claims or {}, "friendly_name": f"{friendly} Claims"}}


def _light(name):
    return {"attributes": {"friendly_name": name}}


# Upstairs has the Bedroom; Downstairs the Kitchen, with two zones placed
# there through their devices; the Study is on no floor; the Attic zone has
# no area at all. The Bedroom zone is placed by name.
HOUSE = {
    "states": {
        "sensor.bedroom_flare_claims": _claims("Bedroom", {"light.landing": {}}),
        "sensor.kitchen_main_flare_claims": _claims("Kitchen Main"),
        "sensor.kitchen_island_flare_claims": _claims("Kitchen Island"),
        "sensor.study_flare_claims": _claims("Study"),
        "sensor.attic_flare_claims": _claims("Attic"),
        "light.bed_lamp": _light("Bed Lamp"),
        "light.bed_ceiling": _light("Bed Ceiling"),
        "light.landing": _light("Landing"),
        "light.k1": _light("Kitchen 1"),
        "light.k2": _light("Kitchen 2"),
        "light.k3": _light("Kitchen 3"),
        "light.k4": _light("Kitchen 4"),
        "light.kitchen_flare": _light("Kitchen"),
        "light.kitchen_indicator": _light("Kitchen Indicator"),
    },
    "floors": {
        "upstairs": {"floor_id": "upstairs", "name": "Upstairs", "level": 1, "icon": "mdi:home-floor-1"},
        "downstairs": {"floor_id": "downstairs", "name": "Downstairs", "level": 0, "icon": None},
    },
    "areas": {
        "bedroom": {"area_id": "bedroom", "name": "Bedroom", "floor_id": "upstairs"},
        "kitchen": {"area_id": "kitchen", "name": "Kitchen", "floor_id": "downstairs"},
        "study": {"area_id": "study", "name": "Study", "floor_id": None},
    },
    "devices": {
        "zone_kitchen_main": {"area_id": "kitchen"},
        "zone_kitchen_island": {"area_id": "kitchen"},
        "bed_lamp_device": {"area_id": "bedroom"},
    },
    "entities": {
        "sensor.bedroom_flare_claims": {"entity_id": "sensor.bedroom_flare_claims", "device_id": "zone_bedroom"},
        "sensor.kitchen_main_flare_claims": {"entity_id": "sensor.kitchen_main_flare_claims", "device_id": "zone_kitchen_main"},
        "sensor.kitchen_island_flare_claims": {"entity_id": "sensor.kitchen_island_flare_claims", "device_id": "zone_kitchen_island"},
        "light.bed_lamp": {"entity_id": "light.bed_lamp", "device_id": "bed_lamp_device"},
        "light.bed_ceiling": {"entity_id": "light.bed_ceiling", "area_id": "bedroom"},
        "light.k1": {"entity_id": "light.k1", "area_id": "kitchen"},
        "light.k2": {"entity_id": "light.k2", "area_id": "kitchen"},
        "light.k3": {"entity_id": "light.k3", "area_id": "kitchen"},
        "light.k4": {"entity_id": "light.k4", "area_id": "kitchen"},
        "light.kitchen_flare": {"entity_id": "light.kitchen_flare", "area_id": "kitchen", "platform": "flare"},
        "light.kitchen_indicator": {"entity_id": "light.kitchen_indicator", "area_id": "kitchen", "entity_category": "diagnostic"},
    },
    "config": {"components": ["logbook"]},
}


@pytest.fixture(scope="module")
def view():
    return run_js(
        f"""
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
await import({js_path(WWW / "flare-view-strategy.js")});
return await defined['ll-strategy-view-flare-zone'].generate({{}}, input);
""",
        HOUSE,
    )


def _headings(section, style=None):
    return [c["heading"] for c in section["cards"] if c["type"] == "heading" and c.get("heading_style") == style]


def test_the_totals_come_first(view):
    totals = view["sections"][0]
    content = totals["cards"][1]["content"]

    assert totals["column_span"] == 2
    assert "sensor.attic_flare_controlled" in content and "sensor.bedroom_flare_overridden" in content
    assert "lights controlled" in content and "overridden" in content


def test_zones_are_grouped_by_floor_then_area(view):
    """Floors by level; then areas on no floor; then zones with no area."""
    assert [s["cards"][0]["heading"] for s in view["sections"][1:]] == ["Downstairs", "Upstairs", "Other areas", "Other zones"]
    assert [s["cards"][0].get("icon") for s in view["sections"][1:3]] == ["mdi:home-floor-0", "mdi:home-floor-1"]


def test_a_zone_takes_its_areas_name_unless_it_shares_the_area(view):
    downstairs, upstairs, other_areas, other_zones = view["sections"][1:]

    assert _headings(downstairs, "subtitle") == ["Kitchen Island", "Kitchen Main"]
    assert _headings(upstairs, "subtitle") == ["Bedroom"]
    assert _headings(other_areas, "subtitle") == ["Study"]
    assert _headings(other_zones, "subtitle") == ["Attic"]


def test_clear_sits_where_the_light_dashboard_has_all_off(view):
    """Its own control in the left third on wide screens; a button on the
    heading on narrow ones."""
    upstairs = view["sections"][2]
    heading = next(c for c in upstairs["cards"] if c.get("heading") == "Bedroom")
    clear = next(c for c in upstairs["cards"] if c.get("entity") == "button.bedroom_flare_clear")
    press = {"action": "perform-action", "perform_action": "button.press", "target": {"entity_id": "button.bedroom_flare_clear"}}

    assert clear["type"] == "custom:flare-clear-card"
    assert clear["visibility"] == [{"condition": "view_columns", "min": 2}]
    assert clear["grid_options"] == {"columns": 3, "rows": 1}
    assert heading["badges"][0]["tap_action"] == press
    assert heading["badges"][0]["visibility"] == [{"condition": "view_columns", "max": 1}]


def test_a_zones_row_is_clear_then_its_two_counts(view):
    """The counts share one card, so on wide screens they fill the rest of
    Clear's row rather than wrapping under it."""
    downstairs = view["sections"][1]
    start = next(i for i, c in enumerate(downstairs["cards"]) if c.get("heading") == "Kitchen Main")
    clear, wide, narrow, names = downstairs["cards"][start + 1 : start + 5]
    counts = ["sensor.kitchen_main_flare_controlled", "sensor.kitchen_main_flare_overridden"]

    assert clear["entity"] == "button.kitchen_main_flare_clear"
    assert clear["grid_options"]["columns"] + wide["grid_options"]["columns"] == 12
    assert [c["entity"] for c in wide["cards"]] == counts[:1] + counts[1:] * 2
    assert wide["visibility"] == [{"condition": "view_columns", "min": 2}]
    assert narrow["cards"] == wide["cards"]
    assert narrow["grid_options"] == {"columns": "full"}
    assert narrow["visibility"] == [{"condition": "view_columns", "max": 1}]
    assert names["type"] == "markdown"


def test_overridden_is_amber_only_while_it_has_lights(view):
    """One of the two is shown at a time, so the pair still fills the row."""
    downstairs = view["sections"][1]
    counts = next(c for c in downstairs["cards"] if c["type"] == "grid")
    amber, grey = counts["cards"][1:]
    some = {"condition": "numeric_state", "entity": "sensor.kitchen_island_flare_overridden", "above": 0}

    assert (amber["color"], amber["visibility"]) == ("amber", [some])
    assert (grey["color"], grey["visibility"]) == ("grey", [{"condition": "not", "conditions": [some]}])


def test_the_heading_opens_the_zones_device_page(view):
    upstairs = view["sections"][2]
    heading = next(c for c in upstairs["cards"] if c.get("heading") == "Bedroom")

    assert heading["tap_action"] == {"action": "navigate", "navigation_path": "/config/devices/device/zone_bedroom"}


def test_overridden_lights_are_named_only_while_there_are_any(view):
    upstairs = view["sections"][2]
    card = next(c for c in upstairs["cards"] if c["type"] == "markdown")

    assert card["visibility"] == [{"condition": "numeric_state", "entity": "sensor.bedroom_flare_overridden", "above": 0}]
    assert "expand(" in card["content"]


def test_activity_stays_in_the_sidebar(view):
    assert view["sidebar"]["sidebar_label"] == "Activity"
