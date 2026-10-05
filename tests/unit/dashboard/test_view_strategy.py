"""The Lovelace strategies - two views and the dashboard made of them - and
the sections they build."""

import pytest

from custom_components.flare.schedule.coordinator import CURVE_KEYS, TIME_KEYS
from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

SCHEDULE = {"attributes": {"points": [], "friendly_name": "Downstairs"}}
STATES = {
    "sensor.downstairs_flare": SCHEDULE,
    "sensor.upstairs_flare": {"attributes": {"points": [], "friendly_name": "Upstairs"}},
    # A schedule sensor with no friendly name - falls back to the slug.
    "sensor.loft_flare": {"attributes": {"points": []}},
    # The claims sensor's siblings, which must not become sections.
    "sensor.downstairs_flare_claims": {"attributes": {}},
    "sensor.downstairs_flare_controlled": {"attributes": {}},
    "sensor.downstairs_flare_overridden": {"attributes": {}},
    # Someone else's sensor that happens to end the same way.
    "sensor.solar_flare": {"attributes": {}},
    "light.kitchen": {"attributes": {}},
    # Zones: identified by `claims`, named "<Zone> Claims".
    "sensor.bedroom_flare_claims": {
        "attributes": {"claims": {}, "friendly_name": "Bedroom Claims"}
    },
    "sensor.dining_room_flare_claims": {
        "attributes": {"claims": {}, "friendly_name": "Dining Room Claims"}
    },
    # No friendly name - falls back to the title-cased slug.
    "sensor.utility_flare_claims": {"attributes": {"claims": {}}},
    # A zone's count sensors, which aren't zones themselves.
    "sensor.bedroom_flare_controlled": {"attributes": {"lights": []}},
    "sensor.bedroom_flare_overridden": {"attributes": {"lights": []}},
    # Contrived: claims-shaped but carrying `points`. The only case testing
    # the `_flare` suffix check independently of the attribute check.
    "sensor.hallway_flare_claims": {"attributes": {"points": []}},
}


# A house for the Activity feed: the Bedroom zone's claims sensor names its
# device.
ACTIVITY = {
    "states": {
        "sensor.bedroom_flare_claims": {"attributes": {"claims": {}, "friendly_name": "Bedroom Claims"}},
        "sensor.attic_flare_claims": {"attributes": {"claims": {}, "friendly_name": "Attic Claims"}},
    },
    "entities": {
        "sensor.bedroom_flare_claims": {"entity_id": "sensor.bedroom_flare_claims", "device_id": "bedroom_zone"},
        "sensor.attic_flare_claims": {"entity_id": "sensor.attic_flare_claims", "device_id": "attic_zone"},
    },
    "config": {"components": ["logbook"]},
}


# What might go in `sensor:`, including values that mean "no filter".
SLUG_CASES = ["upstairs", "sensor.upstairs_flare", "  upstairs  ", "", "   ", None, 7]


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
// Record registrations, which the shim otherwise drops.
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
const {{ sectionConfig, scheduleSensors, normaliseSlug, listZones, zoneDevices }} = await import({js_path(WWW / "flare-section.js")});
await import({js_path(WWW / "flare-view-strategy.js")});
const Strategy = defined['ll-strategy-view-flare-schedule'];
const Zone = defined['ll-strategy-view-flare-zone'];
const Dashboard = defined['ll-strategy-dashboard-flare'];
const schedulesOnly = Object.fromEntries(Object.entries(input.states).filter(([id, s]) => !('claims' in s.attributes)));
const generate = async (states, config = {{}}) => (Strategy ? await Strategy.generate(config, {{ states }}) : null);
return {{
  section: sectionConfig('ground_floor', 'Ground Floor'),
  sensors: scheduleSensors({{ states: input.states }}),
  registeredAs: Object.keys(defined),
  view: await generate(input.states),
  emptyView: await generate({{}}),
  bySlug: await generate(input.states, {{ sensor: 'upstairs' }}),
  byEntityId: await generate(input.states, {{ sensor: 'sensor.upstairs_flare' }}),
  unknown: await generate(input.states, {{ sensor: 'nosuchroom' }}),
  blankSensor: await generate(input.states, {{ sensor: '   ' }}),
  slugs: input.slugCases.map(normaliseSlug),
  zones: listZones({{ states: input.states }}),
  zone: Zone ? await Zone.generate({{}}, {{ states: input.states }}) : null,
  emptyZones: Zone ? await Zone.generate({{}}, {{ states: {{}} }}) : null,
  dashboard: Dashboard ? await Dashboard.generate({{}}, {{ states: input.states }}) : null,
  dashboardWithoutZones: Dashboard ? await Dashboard.generate({{}}, {{ states: schedulesOnly }}) : null,
  emptyDashboard: Dashboard ? await Dashboard.generate({{}}, {{ states: {{}} }}) : null,
  customStrategies: globalThis.window.customStrategies,
  zoneDevices: zoneDevices(input.activity),
  activityView: Zone ? await Zone.generate({{}}, input.activity) : null,
  noLogbookView: Zone ? await Zone.generate({{}}, {{ ...input.activity, config: {{ components: [] }} }}) : null,
}};""",
        {"states": STATES, "slugCases": SLUG_CASES, "activity": ACTIVITY},
    )


def _cards(section):
    return section["cards"]


def _tiles(section):
    """Including those inside the nested grid cards."""
    found = []
    for card in _cards(section):
        if card.get("type") == "tile":
            found.append(card)
        elif card.get("type") == "grid":
            found.extend(c for c in card["cards"] if c.get("type") == "tile")
    return found


def test_the_strategy_is_registered_under_the_name_ha_resolves(result):
    """Otherwise the view renders nothing, with no error."""
    assert "ll-strategy-view-flare-schedule" in result["registeredAs"]


def test_a_view_is_one_section_per_schedule_sensor(result):
    view = result["view"]

    assert view["type"] == "sections"
    assert len(view["sections"]) == 3


def test_sections_are_named_and_ordered_by_the_sensors_own_name(result):
    headings = [s["cards"][0]["heading"] for s in result["view"]["sections"]]

    assert headings == ["Downstairs", "Loft", "Upstairs"]


def test_only_schedule_sensors_become_sections(result):
    """Not the claims sensors, and not someone else's sensor.solar_flare."""
    slugs = [s["slug"] for s in result["sensors"]]

    assert slugs == ["downstairs", "loft", "upstairs"]


def test_a_sensor_with_no_friendly_name_falls_back_to_its_slug(result):
    loft = next(s for s in result["sensors"] if s["slug"] == "loft")

    assert loft["title"] == "Loft"


def test_a_view_can_be_limited_to_one_schedule(result):
    view = result["bySlug"]

    assert len(view["sections"]) == 1
    assert view["sections"][0]["cards"][0]["heading"] == "Upstairs"


def test_the_full_entity_id_works_as_well_as_the_slug(result):
    assert result["byEntityId"] == result["bySlug"]


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, "upstairs"), (1, "upstairs"), (2, "upstairs"), (3, None), (4, None), (5, None), (6, None)],
)
def test_a_sensor_value_is_reduced_to_its_slug(result, index, expected):
    """Empty, whitespace and non-strings mean "no filter"."""
    assert result["slugs"][index] == expected


def test_a_blank_sensor_value_still_shows_every_schedule(result):
    assert len(result["blankSensor"]["sections"]) == 3


def test_an_unknown_schedule_names_the_ones_that_exist(result):
    """A typo would otherwise look the same as having no schedules."""
    content = result["unknown"]["sections"][0]["cards"][1]["content"]

    assert "nosuchroom" in content
    for slug in ("downstairs", "loft", "upstairs"):
        assert f"`{slug}`" in content


def test_no_schedules_explains_itself_rather_than_rendering_blank(result):
    view = result["emptyView"]
    content = view["sections"][0]["cards"][1]["content"]

    assert "No FLARE schedules found" in content
    assert "Add schedule" in content


def test_every_schedule_time_and_curve_entity_is_present(result):
    """Checked against the integration's own key lists."""
    entities = {t["entity"] for t in _tiles(result["section"])}

    for key in TIME_KEYS:
        assert f"time.ground_floor_{key}" in entities, f"missing schedule time {key}"
    for key in CURVE_KEYS:
        assert f"number.ground_floor_{key}" in entities, f"missing curve value {key}"

    assert "select.ground_floor_flare_phase" in entities
    assert "switch.ground_floor_sticky_phase_override" in entities


def test_a_schedule_can_be_copied_or_pasted_from_its_section(result):
    cards = [c for c in _cards(result["section"]) if c.get("type") == "custom:flare-schedule-transfer-card"]
    assert [c["sensor"] for c in cards] == ["ground_floor"]


def test_the_slug_reaches_every_entity(result):
    for tile in _tiles(result["section"]):
        assert "ground_floor" in tile["entity"], f"{tile['entity']} does not carry the slug"


def test_the_curve_card_spans_the_section(result):
    """A card in a sections view doesn't inherit the section's width."""
    card = next(c for c in _cards(result["section"]) if c.get("type") == "custom:flare-curve-card")

    assert card["sensor"] == "ground_floor"
    assert card["grid_options"] == {"columns": "full"}


def test_every_curve_value_is_draggable(result):
    curve = [
        t
        for t in _tiles(result["section"])
        if t["entity"].startswith("number.") and not t["entity"].endswith("_transition")
    ]

    assert len(curve) == 8
    for t in curve:
        assert t["features_position"] == "inline", t["entity"]

    brightness = [t for t in curve if t["entity"].endswith("_brightness")]
    assert len(brightness) == 4
    for t in brightness:
        assert t["features"][0]["type"] == "custom:flare-brightness-feature", t["entity"]


def test_each_brightness_slider_is_tinted_by_its_own_phases_colour(result):
    """Brightness borrows its colour from the same phase's Kelvin."""
    brightness = [
        t
        for t in _tiles(result["section"])
        if t["entity"].startswith("number.") and t["entity"].endswith("_brightness")
    ]

    assert len(brightness) == 4
    for t in brightness:
        assert t["features"][0]["tint_from"] == t["entity"].replace("_brightness", "_kelvin")


def test_both_curve_channels_use_flares_own_sliders(result):
    """The built-in slider takes the tile's (phase) colour, not the value's."""
    kelvin = [
        t
        for t in _tiles(result["section"])
        if t["entity"].startswith("number.") and t["entity"].endswith("_kelvin")
    ]

    assert len(kelvin) == 4
    for t in kelvin:
        assert t["features"] == [{"type": "custom:flare-kelvin-feature"}], t["entity"]


def test_no_transition_gets_a_slider(result):
    """0-1440 minutes makes a slider useless; tapping opens a typed box."""
    transitions = [t for t in _tiles(result["section"]) if t["entity"].endswith("_transition")]

    assert len(transitions) == 8
    for t in transitions:
        assert "features" not in t, f"{t['entity']} should be a plain tile"


@pytest.mark.parametrize("group", [0, 1])
def test_a_row_is_exactly_one_phase(result, group):
    """Each row is one phase, Kelvin then brightness. `columns` has to be the
    grid card's: per-tile grid_options wrap differently at different widths."""
    grids = [c for c in _cards(result["section"]) if c.get("type") == "grid"]

    assert len(grids) == 2, "expected a nested grid for each of Curve and Transitions"
    grid = grids[group]
    assert grid["columns"] == 2
    # CLAUDE.md lesson 15: a nested grid implements no getLayoutOptions().
    assert grid["grid_options"] == {"columns": "full"}

    pairs = [grid["cards"][i : i + 2] for i in range(0, len(grid["cards"]), 2)]
    assert [p[0]["name"].split()[0] for p in pairs] == ["Morning", "Day", "Evening", "Night"]
    for first, second in pairs:
        # Colour temperature leads, brightness follows: the colour is
        # decided on the left and carried into the slider on the right,
        # so left-to-right is the order the two are read in.
        assert "kelvin" in first["entity"]
        assert "brightness" in second["entity"]
        assert first["color"] == second["color"], "a row must be a single colour"


@pytest.mark.parametrize(
    ("phase", "color"),
    [("morning", "blue"), ("day", "yellow"), ("evening", "orange"), ("night", "indigo")],
)
def test_a_phase_is_the_same_colour_everywhere_it_appears(result, phase, color):
    """Colour encodes the phase, icon the channel."""
    tiles = [t for t in _tiles(result["section"]) if f"_{phase}_" in t["entity"]]

    assert tiles, f"no tiles found for {phase}"
    for t in tiles:
        assert t["color"] == color, f"{t['entity']} is {t['color']}, expected {color}"


def test_the_heading_shows_the_live_values(result):
    title = _cards(result["section"])[0]
    contents = [b.get("state_content") for b in title["badges"]]

    assert "brightness" in contents
    assert "color_temp" in contents


def test_the_override_badge_only_shows_while_an_override_is_active(result):
    """It's almost always "Auto"."""
    title = _cards(result["section"])[0]
    badge = next(b for b in title["badges"] if b["entity"].startswith("select."))

    assert badge["visibility"] == [
        {"condition": "state", "entity": "select.ground_floor_flare_phase", "state_not": "Auto"}
    ]


# --- The zone view -------------------------------------------------


def test_the_zone_strategy_is_registered_separately(result):
    assert "ll-strategy-view-flare-zone" in result["registeredAs"]


def test_the_zone_name_drops_the_entitys_own_trailing_word(result):
    """"Bedroom Claims" is the sensor; the zone is "Bedroom"."""
    titles = [s["title"] for s in result["zones"]]

    assert "Bedroom" in titles
    assert "Bedroom Claims" not in titles


def test_the_count_sensors_do_not_become_zones_of_their_own(result):
    """Every zone also has _flare_controlled and _flare_overridden sensors."""
    slugs = [s["slug"] for s in result["zones"]]

    assert slugs == ["bedroom", "dining_room", "utility"]


def test_the_two_strategies_do_not_claim_each_others_sensors(result):
    """`sensor.x_flare_claims` ends with `_flare` plus more, so the schedule
    check must be endsWith, not includes."""
    schedule_slugs = {s["slug"] for s in result["sensors"]}
    zone_slugs = {s["slug"] for s in result["zones"]}

    assert schedule_slugs == {"downstairs", "loft", "upstairs"}
    assert zone_slugs == {"bedroom", "dining_room", "utility"}
    assert not schedule_slugs & zone_slugs
    assert not any("hallway" in slug for slug in schedule_slugs | zone_slugs)


def test_no_zones_explains_itself_rather_than_rendering_blank(result):
    content = result["emptyZones"]["sections"][0]["cards"][1]["content"]

    assert "No FLARE zones found" in content
    assert "Add zone" in content


# --- The dashboard -------------------------------------------------------


def test_the_dashboard_is_a_view_per_schedule_then_zones(result):
    views = result["dashboard"]["views"]

    assert [v["title"] for v in views] == ["Downstairs", "Loft", "Upstairs", "Zones"]
    assert [v["strategy"] for v in views] == [
        {"type": "custom:flare-schedule", "sensor": "downstairs"},
        {"type": "custom:flare-schedule", "sensor": "loft"},
        {"type": "custom:flare-schedule", "sensor": "upstairs"},
        {"type": "custom:flare-zone"},
    ]


def test_the_dashboard_has_no_zones_view_without_zones(result):
    assert [v["title"] for v in result["dashboardWithoutZones"]["views"]] == ["Downstairs", "Loft", "Upstairs"]


def test_an_empty_dashboard_explains_itself(result):
    assert result["emptyDashboard"]["views"] == [{"title": "Lighting", "strategy": {"type": "custom:flare-schedule"}}]


def test_the_dashboard_is_offered_under_add_dashboard(result):
    """HA's Add dashboard dialog lists window.customStrategies, and adds
    `custom:` to the type."""
    (entry,) = [s for s in result["customStrategies"] if s["type"] == "flare"]
    assert entry["strategyType"] == "dashboard"
    assert entry["name"] == "FLARE Lighting"
    assert "ll-strategy-dashboard-flare" in result["registeredAs"]


# --- Activity --------------------------------------------------------------


def test_the_zone_view_has_an_activity_feed_of_the_zones_devices(result):
    """The same entries as each zone's own Activity."""
    sidebar = result["activityView"]["sidebar"]
    heading, logbook = sidebar["sections"][0]["cards"]

    assert result["zoneDevices"] == ["attic_zone", "bedroom_zone"]
    assert heading["heading"] == "Activity"
    assert logbook["type"] == "custom:flare-activity-card"
    assert logbook["device_id"] == ["attic_zone", "bedroom_zone"]
    assert (sidebar["content_label"], sidebar["sidebar_label"]) == ("Zones", "Activity")


def test_no_activity_feed_without_the_logbook(result):
    assert "sidebar" not in result["noLogbookView"]
    assert "sidebar" not in result["zone"], "nor without the zones' devices"
