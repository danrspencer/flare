"""
The curve card's participation in Home Assistant's entity-first card
picker (2026.6+).

When someone picks an entity in the picker, HA asks every custom card
whether it has anything to offer for it, via `getEntitySuggestion` on the
`window.customCards` entry. Getting that wrong is invisible in the worst
way: a card that over-claims turns up suggested against entities it
cannot render, and a card that under-claims simply never appears - and
neither shows up as an error anywhere.

The identification is the whole substance of the feature, so that is what
these pin. Every entity this integration creates has "flare" in its name,
including the tracking scope's own three sensors, so the check has to be
narrower than "looks like ours" - see the comments on scheduleSensorSlug
in the card itself.

Driven through node against the real card file, reusing the shims and
runner test_curve_js_parity.py already uses for exactly this - the card
is written as an ES module (add_extra_js_url defaults to es5: false), so
its `export` keywords are inert in production and available here.
"""

import json
import shutil

import pytest

from test_curve_js_parity import CARD_JS, CARD_SHIMS, _node_eval

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


DRIVER = CARD_SHIMS + f"""
const {{ entitySuggestion, scheduleSensorSlug }} = await import({json.dumps(CARD_JS.as_posix())});

const input = JSON.parse(await new Promise((resolve) => {{
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => (buf += c));
  process.stdin.on('end', () => resolve(buf));
}}));

const hass = {{ states: input.states }};

process.stdout.write(JSON.stringify({{
  suggestions: input.entityIds.map((id) => entitySuggestion(hass, id)),
  slugs: input.entityIds.map((id) => scheduleSensorSlug(hass, id)),
  // The registration itself is part of the contract - a perfect
  // suggestion function that never got wired up would pass every
  // assertion below and still do nothing in a real dashboard.
  card: (() => {{
    const entry = globalThis.customCards.find((c) => c.type === 'flare-curve-card');
    return {{
      hasSuggestion: typeof entry.getEntitySuggestion === 'function',
      preview: entry.preview,
      documentationURL: entry.documentationURL,
    }};
  }})(),
}}));
"""

# A schedule sensor is identified by the `points` attribute, so the
# stand-in states below carry one (its contents are irrelevant here -
# only its presence is checked). The tracking siblings deliberately do
# not: they are real entities on this same integration whose names all
# contain "_flare", which is the trap being guarded against.
SCHEDULE_STATE = {"attributes": {"points": [], "phase": "Evening"}}
PLAIN_STATE = {"attributes": {}}

STATES = {
    "sensor.downstairs_flare": SCHEDULE_STATE,
    "sensor.ground_floor_flare": SCHEDULE_STATE,
    # The three tracking-scope sensors, plus the other domains this
    # integration creates for a schedule.
    "sensor.downstairs_flare_tracking": PLAIN_STATE,
    "sensor.downstairs_flare_controlled": PLAIN_STATE,
    "sensor.downstairs_flare_overridden": PLAIN_STATE,
    "select.downstairs_flare_phase": PLAIN_STATE,
    "number.downstairs_morning_brightness": PLAIN_STATE,
    "time.downstairs_morning_time": PLAIN_STATE,
    "switch.downstairs_sticky_phase_override": PLAIN_STATE,
    "button.downstairs_flare_clear": PLAIN_STATE,
    # Someone else's entity that happens to end the same way.
    "sensor.solar_flare": PLAIN_STATE,
    "light.kitchen": PLAIN_STATE,
}

ENTITY_IDS = list(STATES)


@pytest.fixture(scope="module")
def result():
    return _node_eval(DRIVER, {"states": STATES, "entityIds": ENTITY_IDS})


def _by_entity(result, key):
    return dict(zip(ENTITY_IDS, result[key]))


def test_a_schedule_sensor_is_suggested_with_the_sensor_shorthand(result):
    """The suggestion has to be a config the card can actually take -
    `sensor:` is setConfig's own documented shorthand, so this is the
    same shape the docs generator emits rather than a second one."""
    suggestion = _by_entity(result, "suggestions")["sensor.downstairs_flare"]

    assert suggestion is not None
    assert suggestion["config"]["type"] == "custom:flare-curve-card"
    assert suggestion["config"]["sensor"] == "downstairs"


def test_the_suggested_card_is_full_width(result):
    """A card in a sections view does not inherit its section's width and
    renders at roughly a third of it without this (CLAUDE.md lesson 15).
    A suggestion is the one place that knowledge can be applied for the
    user, since they never see the config to fix it themselves."""
    suggestion = _by_entity(result, "suggestions")["sensor.downstairs_flare"]

    assert suggestion["config"]["grid_options"] == {"columns": "full"}


def test_a_multi_word_slug_survives_the_round_trip(result):
    """The slug is the entity_id minus a fixed prefix and suffix, so an
    underscore-bearing name is where an over-eager split() would break."""
    assert _by_entity(result, "slugs")["sensor.ground_floor_flare"] == "ground_floor"


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.downstairs_flare_tracking",
        "sensor.downstairs_flare_controlled",
        "sensor.downstairs_flare_overridden",
    ],
)
def test_the_tracking_scope_sensors_are_not_suggested(result, entity_id):
    """The case a substring test gets wrong. These are real sensors on
    this integration whose entity_ids all contain "_flare", and the curve
    card cannot render any of them - it needs the day-curve `points`
    attribute only the schedule sensor publishes."""
    assert _by_entity(result, "suggestions")[entity_id] is None


@pytest.mark.parametrize(
    "entity_id",
    [
        "select.downstairs_flare_phase",
        "number.downstairs_morning_brightness",
        "time.downstairs_morning_time",
        "switch.downstairs_sticky_phase_override",
        "button.downstairs_flare_clear",
        "light.kitchen",
    ],
)
def test_other_domains_are_not_suggested(result, entity_id):
    assert _by_entity(result, "suggestions")[entity_id] is None


def test_a_foreign_sensor_with_a_matching_name_is_not_suggested(result):
    """Name shape alone is not enough - sensor.solar_flare belongs to
    nobody here. The `points` attribute check is what makes the match
    about this sensor rather than about its name."""
    assert _by_entity(result, "suggestions")["sensor.solar_flare"] is None


def test_the_card_is_registered_with_the_picker_metadata(result):
    """A correct suggestion function that never got attached to the
    customCards entry would satisfy every test above and still do
    nothing in a real dashboard."""
    card = result["card"]

    assert card["hasSuggestion"], "getEntitySuggestion is not wired into window.customCards"
    assert card["preview"] is True
    assert card["documentationURL"] == "https://danrspencer.github.io/flare/"
