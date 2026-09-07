"""
The Lovelace view strategy, and the section layout it builds.

`views: - strategy: {type: custom:flare}` replaces what used to be a
generator on the docs site emitting YAML to paste. That matters for what
these tests are for: the layout is no longer something a user pastes once
and owns, it is regenerated on every dashboard load, so a mistake here
reaches every install on the next update rather than sitting in one
person's config until they re-paste.

The section it produces is checked against the entity IDs the integration
actually creates - coordinator.py's TIME_KEYS and CURVE_KEYS - rather
than a second list here, so adding a curve value without adding it to the
layout fails instead of quietly shipping a section with a missing
control.

Driven through node against the real files, reusing
test_curve_js_parity.py's shims and runner.
"""

import ast
import json
import shutil
from pathlib import Path

import pytest

from test_curve_js_parity import CARD_JS, CARD_SHIMS, _node_eval

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

WWW = CARD_JS.parent
SECTION_JS = WWW / "flare-section.js"
STRATEGY_JS = WWW / "flare-view-strategy.js"


DRIVER = CARD_SHIMS + f"""
// CARD_SHIMS makes customElements.define a no-op, which is right for the
// card tests but loses the registration this one is about. Record it.
globalThis.__definedElements = {{}};
globalThis.customElements.define = (name, cls) => {{
  globalThis.__definedElements[name] = cls;
}};

const {{ sectionConfig, scheduleSensors, normaliseSlug, trackingScopes }} =
  await import({json.dumps(SECTION_JS.as_posix())});
await import({json.dumps(STRATEGY_JS.as_posix())});

const input = JSON.parse(await new Promise((resolve) => {{
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => (buf += c));
  process.stdin.on('end', () => resolve(buf));
}}));

// customElements is stubbed, so grab the class the way HA resolves it
// rather than through the registry. Tolerate it being missing: that is
// precisely the failure the registration test exists to catch, and
// crashing here instead would turn a clean assertion into a collection
// error that says nothing about what broke.
const Strategy = globalThis.__definedElements['ll-strategy-view-flare'];
const Tracking = globalThis.__definedElements['ll-strategy-view-flare-tracking'];
const generate = async (states, config = {{}}) =>
  Strategy ? await Strategy.generate(config, {{ states }}) : null;

process.stdout.write(JSON.stringify({{
  section: sectionConfig('ground_floor', 'Ground Floor'),
  sensors: scheduleSensors({{ states: input.states }}),
  registeredAs: Object.keys(globalThis.__definedElements),
  view: await generate(input.states),
  emptyView: await generate({{}}),
  bySlug: await generate(input.states, {{ sensor: 'upstairs' }}),
  byEntityId: await generate(input.states, {{ sensor: 'sensor.upstairs_flare' }}),
  unknown: await generate(input.states, {{ sensor: 'nosuchroom' }}),
  blankSensor: await generate(input.states, {{ sensor: '   ' }}),
  slugs: input.slugCases.map(normaliseSlug),
  scopes: trackingScopes({{ states: input.states }}),
  tracking: Tracking ? await Tracking.generate({{}}, {{ states: input.states }}) : null,
  emptyTracking: Tracking ? await Tracking.generate({{}}, {{ states: {{}} }}) : null,
}}));
"""

SCHEDULE = {"attributes": {"points": [], "friendly_name": "Downstairs"}}
STATES = {
    "sensor.downstairs_flare": SCHEDULE,
    "sensor.upstairs_flare": {"attributes": {"points": [], "friendly_name": "Upstairs"}},
    # A schedule sensor with no friendly name - falls back to the slug.
    "sensor.loft_flare": {"attributes": {"points": []}},
    # The tracking siblings, which must not become sections.
    "sensor.downstairs_flare_tracking": {"attributes": {}},
    "sensor.downstairs_flare_controlled": {"attributes": {}},
    "sensor.downstairs_flare_overridden": {"attributes": {}},
    # Someone else's sensor that happens to end the same way.
    "sensor.solar_flare": {"attributes": {}},
    "light.kitchen": {"attributes": {}},
    # Tracking scopes. Identified by `claims`, and named "<Scope>
    # Tracking" - the trailing word is the entity's own name, not part
    # of the scope's.
    "sensor.bedroom_flare_tracking": {
        "attributes": {"claims": {}, "friendly_name": "Bedroom Tracking"}
    },
    "sensor.dining_room_flare_tracking": {
        "attributes": {"claims": {}, "friendly_name": "Dining Room Tracking"}
    },
    # No friendly name - falls back to the title-cased slug.
    "sensor.utility_flare_tracking": {"attributes": {"claims": {}}},
    # The count sensors a scope also creates: they must not each become
    # a scope of their own.
    "sensor.bedroom_flare_controlled": {"attributes": {"lights": []}},
    "sensor.bedroom_flare_overridden": {"attributes": {"lights": []}},
    # Contrived on purpose, and the only case that isolates the suffix
    # test from the attribute test: a tracking-shaped id carrying
    # `points`. No real entity looks like this - a tracking sensor has
    # `claims` - which is exactly why it is needed. Without it, relaxing
    # endsWith('_flare') to includes('_flare') passes everything,
    # because every real tracking sensor is already rejected on the
    # missing attribute. Verified by mutation. Same reasoning, and the
    # same shape of fixture, as tests/test_card_suggestion.py.
    "sensor.hallway_flare_tracking": {"attributes": {"points": []}},
}


# Everything someone might reasonably put in `sensor:`, plus the values
# that must read as "no filter" rather than as a slug.
SLUG_CASES = ["upstairs", "sensor.upstairs_flare", "  upstairs  ", "", "   ", None, 7]


@pytest.fixture(scope="module")
def result():
    return _node_eval(DRIVER, {"states": STATES, "slugCases": SLUG_CASES})


def _cards(section):
    return section["cards"]


def _tiles(section):
    """Curve and Transitions live inside nested grid cards, so a flat scan
    of the section's own cards misses two thirds of the tiles."""
    found = []
    for card in _cards(section):
        if card.get("type") == "tile":
            found.append(card)
        elif card.get("type") == "grid":
            found.extend(c for c in card["cards"] if c.get("type") == "tile")
    return found


def _integration_keys(name):
    """CURVE_KEYS / TIME_KEYS read out of coordinator.py without importing
    it - it imports `.const` relatively and would pull in homeassistant,
    which these fast tests avoid. Parsing the literal keeps one source of
    truth with no import."""
    source = (WWW.parent / "coordinator.py").read_text()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in coordinator.py")


def test_the_strategy_is_registered_under_the_name_ha_resolves(result):
    """`custom:flare` on a view resolves to `ll-strategy-view-flare`. Get
    this wrong and the view renders nothing, with no error anywhere."""
    assert "ll-strategy-view-flare" in result["registeredAs"]


def test_a_view_is_one_section_per_schedule_sensor(result):
    """The whole point of the strategy over pasted YAML: adding a schedule
    adds a section, with nothing for the user to do."""
    view = result["view"]

    assert view["type"] == "sections"
    assert len(view["sections"]) == 3


def test_sections_are_named_and_ordered_by_the_sensors_own_name(result):
    headings = [s["cards"][0]["heading"] for s in result["view"]["sections"]]

    assert headings == ["Downstairs", "Loft", "Upstairs"]


def test_only_schedule_sensors_become_sections(result):
    """Every entity this integration creates has "flare" in its name,
    including the tracking scope's own three sensors, so the match has to
    be narrower than that - and `sensor.solar_flare` belongs to nobody
    here. The `points` attribute is what makes it about this sensor
    rather than about its name."""
    slugs = [s["slug"] for s in result["sensors"]]

    assert slugs == ["downstairs", "loft", "upstairs"]


def test_a_sensor_with_no_friendly_name_falls_back_to_its_slug(result):
    loft = next(s for s in result["sensors"] if s["slug"] == "loft")

    assert loft["title"] == "Loft"


def test_a_view_can_be_limited_to_one_schedule(result):
    """One section per view is the shape you want once there is more than
    one schedule - a view per room rather than everything stacked."""
    view = result["bySlug"]

    assert len(view["sections"]) == 1
    assert view["sections"][0]["cards"][0]["heading"] == "Upstairs"


def test_the_full_entity_id_works_as_well_as_the_slug(result):
    """`sensor: downstairs` matches the curve card's shorthand, but
    `sensor.downstairs_flare` is what someone copying from the entity
    list will paste, and neither is wrong."""
    assert result["byEntityId"] == result["bySlug"]


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, "upstairs"), (1, "upstairs"), (2, "upstairs"), (3, None), (4, None), (5, None), (6, None)],
)
def test_a_sensor_value_is_reduced_to_its_slug(result, index, expected):
    """Empty, whitespace and non-strings all have to read as "no filter"
    rather than as a slug that matches nothing - otherwise a stray key
    silently produces the not-found notice instead of every schedule."""
    assert result["slugs"][index] == expected


def test_a_blank_sensor_value_still_shows_every_schedule(result):
    """The consequence of the above at the strategy level."""
    assert len(result["blankSensor"]["sections"]) == 3


def test_an_unknown_schedule_names_the_ones_that_exist(result):
    """A typo would otherwise render an empty view, which looks identical
    to having no schedules at all. The available slugs are the one thing
    the user needs and cannot see from the dashboard."""
    content = result["unknown"]["sections"][0]["cards"][1]["content"]

    assert "nosuchroom" in content
    for slug in ("downstairs", "loft", "upstairs"):
        assert f"`{slug}`" in content


def test_no_schedules_explains_itself_rather_than_rendering_blank(result):
    """Exactly the state someone is in if they add the view before adding
    a schedule. A blank screen gives them nothing to act on."""
    view = result["emptyView"]
    content = view["sections"][0]["cards"][1]["content"]

    assert "No FLARE schedules found" in content
    assert "Add schedule sensor" in content


def test_every_schedule_time_and_curve_entity_is_present(result):
    """Checked against the integration's own key lists, so adding a curve
    value without adding it here fails rather than silently shipping a
    section with a missing control."""
    TIME_KEYS = _integration_keys("TIME_KEYS")
    CURVE_KEYS = _integration_keys("CURVE_KEYS")
    assert len(TIME_KEYS) == 5 and len(CURVE_KEYS) == 16, "parsed the wrong thing"

    entities = {t["entity"] for t in _tiles(result["section"])}

    for key in TIME_KEYS:
        assert f"time.ground_floor_{key}" in entities, f"missing schedule time {key}"
    for key in CURVE_KEYS:
        assert f"number.ground_floor_{key}" in entities, f"missing curve value {key}"

    assert "select.ground_floor_flare_phase" in entities
    assert "switch.ground_floor_sticky_phase_override" in entities


def test_the_slug_reaches_every_entity(result):
    """A tile left pointing at another schedule's entity is invisible in
    review and renders as unavailable - and now that one view holds every
    schedule, it would point at a real entity of the wrong room."""
    for tile in _tiles(result["section"]):
        assert "ground_floor" in tile["entity"], f"{tile['entity']} does not carry the slug"


def test_the_curve_card_spans_the_section(result):
    """Without columns: full a card in a sections view renders at roughly
    a third width - see CLAUDE.md lesson 15."""
    card = next(c for c in _cards(result["section"]) if c.get("type") == "custom:flare-curve-card")

    assert card["sensor"] == "ground_floor"
    assert card["grid_options"] == {"columns": "full"}


def test_every_curve_value_is_draggable(result):
    """This section is a control panel, not a readout."""
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
        assert t["features"] == [{"type": "numeric-input", "style": "slider"}], t["entity"]


def test_colour_temperature_uses_flares_own_slider(result):
    """The built-in slider paints itself from the tile's colour, which
    this section spends on encoding the phase."""
    kelvin = [
        t
        for t in _tiles(result["section"])
        if t["entity"].startswith("number.") and t["entity"].endswith("_kelvin")
    ]

    assert len(kelvin) == 4
    for t in kelvin:
        assert t["features"] == [{"type": "custom:flare-kelvin-feature"}], t["entity"]


def test_no_transition_gets_a_slider(result):
    """A transition runs 0-1440 minutes while every value anyone sets is
    under an hour, so a slider spends ~96% of its travel out of reach.
    These fall through to the more-info dialog, which number.py already
    renders as a typed box."""
    transitions = [t for t in _tiles(result["section"]) if t["entity"].endswith("_transition")]

    assert len(transitions) == 8
    for t in transitions:
        assert "features" not in t, f"{t['entity']} should be a plain tile"


@pytest.mark.parametrize("group", [0, 1])
def test_a_row_is_exactly_one_phase(result, group):
    """Curve and Transitions are nested grid cards at two columns, so each
    row is one phase's brightness beside its colour, in day order.

    Two columns has to be a property of the grid CARD, which is absolute.
    Per-tile grid_options count against the section's own grid, which is
    12 wide times its column_span (4 here), so a fixed per-tile value
    lands on a different number of tiles per row at different widths."""
    grids = [c for c in _cards(result["section"]) if c.get("type") == "grid"]

    assert len(grids) == 2, "expected a nested grid for each of Curve and Transitions"
    grid = grids[group]
    assert grid["columns"] == 2
    # CLAUDE.md lesson 15: a nested grid implements no getLayoutOptions().
    assert grid["grid_options"] == {"columns": "full"}

    pairs = [grid["cards"][i : i + 2] for i in range(0, len(grid["cards"]), 2)]
    assert [p[0]["name"].split()[0] for p in pairs] == ["Morning", "Day", "Evening", "Night"]
    for first, second in pairs:
        assert "brightness" in first["entity"]
        assert "kelvin" in second["entity"]
        assert first["color"] == second["color"], "a row must be a single colour"


@pytest.mark.parametrize(
    ("phase", "color"),
    [("morning", "blue"), ("day", "yellow"), ("evening", "orange"), ("night", "indigo")],
)
def test_a_phase_is_the_same_colour_everywhere_it_appears(result, phase, color):
    """Colour encodes the phase and icon encodes the channel, so a phase
    that is blue in the Curve group and orange in Transitions would break
    the one property that makes the section scannable."""
    tiles = [t for t in _tiles(result["section"]) if f"_{phase}_" in t["entity"]]

    assert tiles, f"no tiles found for {phase}"
    for t in tiles:
        assert t["color"] == color, f"{t['entity']} is {t['color']}, expected {color}"


def test_the_heading_shows_the_live_values(result):
    """Phase, brightness and colour temperature read straight off the
    schedule sensor, so the header answers "what is it doing right now"
    without opening anything."""
    title = _cards(result["section"])[0]
    contents = [b.get("state_content") for b in title["badges"]]

    assert "brightness" in contents
    assert "color_temp" in contents


def test_the_override_badge_only_shows_while_an_override_is_active(result):
    """It reads "Auto" the vast majority of the time, which is noise on a
    header whose job is to show what is actually happening."""
    title = _cards(result["section"])[0]
    badge = next(b for b in title["badges"] if b["entity"].startswith("select."))

    assert badge["visibility"] == [
        {"condition": "state", "entity": "select.ground_floor_flare_phase", "state_not": "Auto"}
    ]


# --- The tracking view -------------------------------------------------


def _tracking_section(result, index=0):
    return result["tracking"]["sections"][index]


def test_the_tracking_strategy_is_registered_separately(result):
    """`custom:flare-tracking` resolves to its own element. Registering
    only one of the two renders an empty view with no error."""
    assert "ll-strategy-view-flare-tracking" in result["registeredAs"]


def test_a_tracking_view_is_one_section_per_scope(result):
    headings = [s["cards"][0]["heading"] for s in result["tracking"]["sections"]]

    assert headings == ["Bedroom", "Dining Room", "Utility"]


def test_the_scope_name_drops_the_entitys_own_trailing_word(result):
    """The sensor is called "Bedroom Tracking"; the scope is "Bedroom".
    Leaving it on gives a section headed "Bedroom Tracking" above a tile
    already labelled Controlled, which reads as a stutter."""
    titles = [s["title"] for s in result["scopes"]]

    assert "Bedroom" in titles
    assert "Bedroom Tracking" not in titles


def test_the_count_sensors_do_not_become_scopes_of_their_own(result):
    """Every scope creates `_flare_controlled` and `_flare_overridden`
    alongside `_flare_tracking`. Matching loosely would turn one room
    into three sections."""
    slugs = [s["slug"] for s in result["scopes"]]

    assert slugs == ["bedroom", "dining_room", "utility"]


def test_the_two_strategies_do_not_claim_each_others_sensors(result):
    """`sensor.x_flare_tracking` ends with `_flare` PLUS MORE, so the
    schedule test has to be endsWith, not includes.

    `sensor.hallway_flare_tracking` in the fixture carries `points` for
    this test alone: every real tracking sensor is rejected on the
    missing attribute instead, so without it the suffix could be relaxed
    and nothing would notice. It must land in neither view - wrong shape
    for a schedule, wrong attribute for a scope."""
    schedule_slugs = {s["slug"] for s in result["sensors"]}
    tracking_slugs = {s["slug"] for s in result["scopes"]}

    assert schedule_slugs == {"downstairs", "loft", "upstairs"}
    assert tracking_slugs == {"bedroom", "dining_room", "utility"}
    assert not schedule_slugs & tracking_slugs
    assert not any("hallway" in slug for slug in schedule_slugs | tracking_slugs)


def test_a_scope_shows_both_counts_and_a_clear_button(result):
    entities = [c.get("entity") for c in _tracking_section(result)["cards"]]

    assert "sensor.bedroom_flare_controlled" in entities
    assert "sensor.bedroom_flare_overridden" in entities
    assert "button.bedroom_flare_clear" in entities


def test_the_clear_button_presses_rather_than_opening_a_dialog(result):
    """An explicit tap_action, not the tile card's per-domain default:
    pressing is the only thing anyone wants from this tile, and a default
    that changes upstream would silently turn it into a more-info
    dialog."""
    clear = next(
        c for c in _tracking_section(result)["cards"] if c.get("entity", "").startswith("button.")
    )

    assert clear["tap_action"] == {
        "action": "perform-action",
        "perform_action": "button.press",
        "target": {"entity_id": "button.bedroom_flare_clear"},
    }


def test_the_overridden_lights_are_named_only_while_there_are_any(result):
    """Naming them is the reason to open this view - "which light stopped
    following". Showing an empty line the rest of the time would make
    every section a line taller for nothing, so it is hidden at zero."""
    card = next(c for c in _tracking_section(result)["cards"] if c.get("type") == "markdown")

    assert card["visibility"] == [
        {"condition": "numeric_state", "entity": "sensor.bedroom_flare_overridden", "above": 0}
    ]
    # expand() turns the entity_ids into states so real names show, and
    # the `or []` keeps it from throwing before the attribute exists.
    assert "expand(" in card["content"]
    assert "or []" in card["content"]


def test_no_scopes_explains_itself_rather_than_rendering_blank(result):
    content = result["emptyTracking"]["sections"][0]["cards"][1]["content"]

    assert "No FLARE tracking scopes found" in content
    assert "Add state device" in content
