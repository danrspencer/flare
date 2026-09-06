"""
The docs site's dashboard section generator.

Its whole output is YAML a user pastes straight into a Home Assistant
raw config editor, which makes two failure modes possible that nothing
else here would catch: YAML that doesn't parse (HA rejects the paste
outright), and YAML that parses but names an entity the integration
never creates (HA accepts it and silently renders an unavailable tile).

Neither is hypothetical now that the section is built from data rather
than spelled out tile by tile - the whole point of that shape is that
one edit reaches all four phases at once, which is equally true of one
mistake.

The entity IDs are checked against the same key lists the integration
builds its entities from - coordinator.py's TIME_KEYS and CURVE_KEYS -
rather than a second copy of them here, so a renamed or added curve
value fails this test instead of quietly producing a dashboard section
that is missing a control.
"""

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

GENERATOR_JS = (
    Path(__file__).resolve().parent.parent / "docs" / "assets" / "js" / "dashboard-generator.js"
)

# The module wires itself to the page at import time. Stub just enough
# DOM for that to be a no-op, the same shape as test_curve_js_parity.py's
# CARD_SHIMS - the goal is to reach the pure buildYaml, not to simulate a
# browser.
#
# Only `document` is stubbed: navigator.clipboard and setTimeout are
# reached solely from the copy button's click handler, which never runs
# here. Node also makes globalThis.navigator read-only, so assigning it
# would throw on import and take the whole module with it.
DOM_SHIMS = """
const el = { addEventListener() {}, value: '', textContent: '' };
globalThis.document = { getElementById: () => el, querySelectorAll: () => [] };
"""

DRIVER = DOM_SHIMS + f"""
const {{ buildYaml }} = await import({json.dumps(GENERATOR_JS.as_posix())});
process.stdout.write(buildYaml('ground_floor', 'Ground Floor'));
"""


@pytest.fixture(scope="module")
def section():
    result = subprocess.run(
        ["node", "--input-type=module", "-e", DRIVER],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"node failed:\n{result.stderr}")
    return result.stdout


@pytest.fixture(scope="module")
def parsed(section):
    return yaml.safe_load(section)


def _cards(parsed):
    return parsed["cards"]


def _tiles(parsed):
    """Curve and Transitions live inside nested grid cards, so a flat scan
    of the section's own cards misses two thirds of the tiles."""
    found = []
    for card in _cards(parsed):
        if card.get("type") == "tile":
            found.append(card)
        elif card.get("type") == "grid":
            found.extend(c for c in card["cards"] if c.get("type") == "tile")
    return found


def _entities(parsed):
    return [c["entity"] for c in _tiles(parsed)]


def test_the_output_is_valid_yaml(parsed):
    """The single thing that makes the generator worthless if wrong -
    Home Assistant rejects an unparseable paste outright."""
    assert parsed["type"] == "grid"
    assert parsed["column_span"] == 4
    assert _cards(parsed), "no cards were generated"


def _integration_keys(name):
    """CURVE_KEYS / TIME_KEYS read out of coordinator.py without importing
    it. The sys.path trick tests/conftest.py uses for curve.py doesn't
    work here - coordinator.py imports `.const` relatively and pulls in
    homeassistant, which is exactly what these fast pure tests avoid. So
    parse the literal instead: still one source of truth, no import."""
    source = (
        Path(__file__).resolve().parent.parent / "custom_components" / "flare" / "coordinator.py"
    ).read_text()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in coordinator.py")


def test_every_schedule_time_and_curve_entity_is_present(parsed):
    """Checked against the integration's own key lists, so adding a curve
    value without adding it here fails rather than silently shipping a
    section with a missing control."""
    TIME_KEYS = _integration_keys("TIME_KEYS")
    CURVE_KEYS = _integration_keys("CURVE_KEYS")
    assert len(TIME_KEYS) == 5 and len(CURVE_KEYS) == 16, "parsed the wrong thing"

    entities = set(_entities(parsed))

    for key in TIME_KEYS:
        assert f"time.ground_floor_{key}" in entities, f"missing schedule time {key}"
    for key in CURVE_KEYS:
        assert f"number.ground_floor_{key}" in entities, f"missing curve value {key}"

    assert "select.ground_floor_flare_phase" in entities
    assert "switch.ground_floor_sticky_phase_override" in entities


def test_the_slug_reaches_every_entity(parsed):
    """A tile left pointing at another schedule's entity is invisible in
    review and renders as unavailable for the user."""
    for entity in _entities(parsed):
        assert "ground_floor" in entity, f"{entity} does not carry the slug"


def test_the_curve_card_spans_the_section(parsed):
    """Without columns: full a card in a sections view renders at roughly
    a third width - see CLAUDE.md lesson 15."""
    card = next(c for c in _cards(parsed) if c.get("type") == "custom:flare-curve-card")

    assert card["sensor"] == "ground_floor"
    assert card["grid_options"] == {"columns": "full"}


def test_every_curve_value_is_draggable(parsed):
    """The reason this section uses tiles rather than the read-only gauge
    cards it started with: it is a control panel, not a readout."""
    curve_tiles = [
        t
        for t in _tiles(parsed)
        if t["entity"].startswith("number.") and not t["entity"].endswith("_transition")
    ]

    assert len(curve_tiles) == 8
    for t in curve_tiles:
        assert t["features_position"] == "inline", t["entity"]

    brightness = [t for t in curve_tiles if t["entity"].endswith("_brightness")]
    kelvin = [t for t in curve_tiles if t["entity"].endswith("_kelvin")]
    assert len(brightness) == 4 and len(kelvin) == 4

    for t in brightness:
        assert t["features"] == [{"type": "numeric-input", "style": "slider"}], t["entity"]


def test_colour_temperature_uses_flares_own_slider(parsed):
    """The built-in slider paints itself from --feature-color, which
    hui-tile-card sets to the tile's own colour - and this section spends
    that on encoding the phase. FLARE's feature paints its own track in
    the temperature it sets, so the tile colour goes back to meaning just
    the icon. It ships inside the integration, so the section still needs
    nothing extra installed."""
    kelvin = [
        t
        for t in _tiles(parsed)
        if t["entity"].startswith("number.") and t["entity"].endswith("_kelvin")
    ]

    assert len(kelvin) == 4
    for t in kelvin:
        assert t["features"] == [{"type": "custom:flare-kelvin-feature"}], t["entity"]


def test_no_transition_gets_a_slider(parsed):
    """A transition runs 0-1440 minutes while every value anyone sets is
    under an hour, so a slider spends ~96% of its travel out of reach and
    a pixel is worth several minutes. These fall through to the more-info
    dialog instead, which number.py already renders as a typed box
    (_attr_mode = "box") rather than a second slider."""
    transitions = [t for t in _tiles(parsed) if t["entity"].endswith("_transition")]

    assert len(transitions) == 8
    for t in transitions:
        assert "features" not in t, f"{t['entity']} should be a plain tile"
        assert "features_position" not in t, t["entity"]


def test_the_interactive_controls_carry_a_feature(parsed):
    """Phase and Sticky are both directly actionable from the tile rather
    than tap-to-open. The five schedule times deliberately are not - a
    `time` entity has no inline-editable feature, so tapping to open the
    time picker is the best available option."""
    by_entity = {t["entity"]: t for t in _tiles(parsed)}

    assert by_entity["select.ground_floor_flare_phase"]["features"] == [{"type": "select-options"}]
    assert by_entity["switch.ground_floor_sticky_phase_override"]["features"] == [{"type": "toggle"}]
    for entity, t in by_entity.items():
        if entity.startswith("time."):
            assert "features" not in t, f"{entity} should stay a plain tile"


@pytest.mark.parametrize(
    ("phase", "color"),
    [("morning", "blue"), ("day", "yellow"), ("evening", "orange"), ("night", "indigo")],
)
def test_a_phase_is_the_same_colour_everywhere_it_appears(parsed, phase, color):
    """Colour encodes the phase and icon encodes the channel, so a phase
    that is amber in the Curve group and orange in Transitions would
    break the one property that makes the section scannable."""
    tiles = [t for t in _tiles(parsed) if f"_{phase}_" in t["entity"] or t["entity"].endswith(f"_{phase}_time")]

    assert tiles, f"no tiles found for {phase}"
    for t in tiles:
        assert t["color"] == color, f"{t['entity']} is {t['color']}, expected {color}"


@pytest.mark.parametrize("group", [0, 1])
def test_a_row_is_exactly_one_phase(parsed, group):
    """Curve and Transitions are nested grid cards at two columns, so each
    row is one phase's brightness beside its colour, in day order.

    Two columns is a property of the *grid card*, which is absolute.
    Per-tile grid_options would not do: those count against the section's
    own grid, which is 12 wide times its column_span (4 here), so a fixed
    per-tile value lands on a different number of tiles per row at
    different window widths - and this layout is entirely about which two
    tiles end up adjacent."""
    grids = [c for c in _cards(parsed) if c.get("type") == "grid"]

    assert len(grids) == 2, "expected a nested grid for each of Curve and Transitions"
    grid = grids[group]
    assert grid["columns"] == 2
    # CLAUDE.md lesson 15: a nested grid implements no getLayoutOptions(),
    # so without this the whole group renders at roughly a third width.
    assert grid["grid_options"] == {"columns": "full"}

    pairs = [grid["cards"][i : i + 2] for i in range(0, len(grid["cards"]), 2)]
    assert [p[0]["name"].split()[0] for p in pairs] == ["Morning", "Day", "Evening", "Night"]
    for first, second in pairs:
        assert "brightness" in first["entity"]
        assert "kelvin" in second["entity"]
        assert first["color"] == second["color"], "a row must be a single colour"


def test_the_heading_shows_the_live_values(parsed):
    """Phase, brightness and colour temperature read straight off the
    schedule sensor, so the header answers "what is it doing right now"
    without opening anything. state_content takes an attribute name."""
    headings = [c for c in _cards(parsed) if c.get("type") == "heading"]
    title = headings[0]
    contents = [b.get("state_content") for b in title["badges"]]

    assert "brightness" in contents
    assert "color_temp" in contents
    assert all(
        b["entity"].startswith("sensor.ground_floor_flare") or b["entity"].startswith("select.")
        for b in title["badges"]
    )


def test_the_override_badge_only_shows_while_an_override_is_active(parsed):
    """It reads "Auto" the vast majority of the time, which is noise on a
    header whose job is to show what is actually happening."""
    title = next(c for c in _cards(parsed) if c.get("type") == "heading")
    badge = next(b for b in title["badges"] if b["entity"].startswith("select."))

    assert badge["visibility"] == [
        {"condition": "state", "entity": "select.ground_floor_flare_phase", "state_not": "Auto"}
    ]
