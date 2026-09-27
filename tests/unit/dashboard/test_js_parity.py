"""The JS copies of curve.py's maths must agree with it exactly:
docs/assets/js/curve.js (the docs playground) and the curve card's
phaseAt/phaseMarks/kelvinToRgb.

The grid includes exact .5 ties in the ramps, where Python's round()
(half-to-even) and JS's Math.round() (half-up) disagree. kelvinToRgb has
no .5 ties at integer Kelvin, so the RGB sweep pins the algorithm, not
the rounding rule.
"""

from custom_components.flare.schedule.curve import (
    DEFAULT_CURVE_VALUES,
    brightness_for_phase,
    kelvin_for_phase,
    kelvin_to_rgb,
    phase_at,
    phase_marks,
)
from tests.support import REPO_ROOT, WWW
from tests.support.node import js_path, requires_node, run_js

pytestmark = requires_node

CURVE_JS = js_path(REPO_ROOT / "docs" / "assets" / "js" / "curve.js")
CARD_JS = js_path(WWW / "flare-curve-card.js")
KELVINS = list(range(1000, 10001))

# Normal days plus awkward ones: a very short Day, and an Evening too short
# for its hold.
BOUNDARY_SETS = [
    {"morningTs": 6 * 3600, "dayStartTs": 8 * 3600, "eveningTs": 19.75 * 3600, "nightTs": 22 * 3600},
    {"morningTs": 5 * 3600, "dayStartTs": 7 * 3600, "eveningTs": 17 * 3600, "nightTs": 23 * 3600},
    {"morningTs": 6 * 3600, "dayStartTs": 8 * 3600, "eveningTs": 8.25 * 3600, "nightTs": 22 * 3600},
    {"morningTs": 6 * 3600, "dayStartTs": 8 * 3600, "eveningTs": 20 * 3600, "nightTs": 21.5 * 3600},
]

# Odd endpoints over even steps land ramps on .5 ties.
CURVE_VALUE_SETS = [
    dict(DEFAULT_CURVE_VALUES),
    {**DEFAULT_CURVE_VALUES, "evening_brightness": 161, "night_brightness": 80},
    {**DEFAULT_CURVE_VALUES, "morning_kelvin": 6501, "day_kelvin": 4001, "evening_kelvin": 3001, "night_kelvin": 2701},
    {**DEFAULT_CURVE_VALUES, "evening_brightness": 3, "night_brightness": 254, "morning_kelvin": 2000, "day_kelvin": 6500},
    {**DEFAULT_CURVE_VALUES, "evening_kelvin_transition": 0, "evening_brightness_transition": 0},
    {**DEFAULT_CURVE_VALUES, "night_kelvin_transition": 1440, "morning_brightness_transition": 1440},
    {**DEFAULT_CURVE_VALUES, "day_kelvin_transition": 37, "evening_brightness_transition": 91},
]

_H = 3600
MARK_CASES = [
    [6 * _H, 8 * _H, 19 * _H, 22 * _H],
    [10 * _H, 8 * _H, 19 * _H, 22 * _H],
    [6 * _H, 8 * _H, 7 * _H, 22 * _H],
    [6 * _H, 8 * _H, 19 * _H, 18 * _H],
    [6 * _H, 6 * _H, 19 * _H, 22 * _H],
    [6 * _H, 8 * _H, 8 * _H, 22 * _H],
    [22 * _H, 20 * _H, 18 * _H, 16 * _H],
    [0, 8 * _H, 19 * _H, 22 * _H],
    [6 * _H, 6 * _H, 6 * _H, 6 * _H],
    [0, 0, 0, 86399],
]


def _instants(boundaries):
    """Every 5 minutes, plus each boundary and a second either side."""
    instants = [i * 300 for i in range(289)]
    for key in ("morningTs", "dayStartTs", "eveningTs", "nightTs"):
        b = boundaries[key]
        instants.extend([b - 1, b, b + 1])
    instants.extend([boundaries["nightTs"] - 3600, boundaries["eveningTs"] + 3600])
    return sorted(set(float(t) for t in instants))


def _only(values, word):
    return {k: v for k, v in values.items() if word in k}


def _rgb_mismatches(js_rgb):
    return [f"{k}: py={tuple(kelvin_to_rgb(k))} js={tuple(got)}" for k, got in zip(KELVINS, js_rgb) if tuple(kelvin_to_rgb(k)) != tuple(got)]


def test_docs_curve_js_matches_curve_py():
    cases = [
        {"boundaries": b, "values": v, "t": t, "phase": phase}
        for b in BOUNDARY_SETS
        for v in CURVE_VALUE_SETS
        for t in _instants(b)
        for phase in ("Morning", "Day", "Evening", "Night")
    ]
    js = run_js(
        f"""
const {{ phaseAt, brightnessForPhase, kelvinForPhase, kelvinToRgb }} = await import({CURVE_JS});
return {{
  out: input.cases.map((c) => {{
    const b = c.boundaries;
    return [
      phaseAt(c.t, b.morningTs, b.dayStartTs, b.eveningTs, b.nightTs),
      brightnessForPhase(c.phase, c.t, b, c.values),
      kelvinForPhase(c.phase, c.t, b, c.values),
    ];
  }}),
  rgb: input.kelvins.map(kelvinToRgb),
}};""",
        {"cases": cases, "kelvins": KELVINS},
    )
    assert len(js["out"]) == len(cases)

    mismatches = []
    for case, (js_phase, js_brightness, js_kelvin) in zip(cases, js["out"]):
        b, v, t, phase = case["boundaries"], case["values"], case["t"], case["phase"]
        args = (b["morningTs"], b["dayStartTs"], b["eveningTs"], b["nightTs"])
        expected = (
            phase_at(t, *args),
            brightness_for_phase(phase, t, *args, **_only(v, "brightness")),
            kelvin_for_phase(phase, t, *args, **_only(v, "kelvin")),
        )
        if expected != (js_phase, js_brightness, js_kelvin):
            mismatches.append(f"{phase} t={t} {b} {v}: py={expected} js={(js_phase, js_brightness, js_kelvin)}")
    assert not mismatches, "curve.js has drifted from curve.py:\n" + "\n".join(mismatches[:20])
    assert not _rgb_mismatches(js["rgb"]), "\n".join(_rgb_mismatches(js["rgb"])[:20])


def test_docs_curve_js_defaults_match_curve_py():
    js = run_js(f"return (await import({CURVE_JS})).DEFAULT_CURVE_VALUES;")
    assert js == DEFAULT_CURVE_VALUES


def test_docs_build_points_produces_a_full_varying_day():
    """buildPoints is what the playground renders; the grid above doesn't
    reach it."""
    result = run_js(
        f"""
const {{ buildPoints, DEFAULT_CURVE_VALUES }} = await import({CURVE_JS});
const boundaries = {{ morningTs: 6 * 3600, dayStartTs: 8 * 3600, eveningTs: 18 * 3600, nightTs: 22 * 3600 }};
return [
  DEFAULT_CURVE_VALUES,
  {{ ...DEFAULT_CURVE_VALUES, day_kelvin_transition: 0, evening_brightness_transition: 0 }},
  {{ ...DEFAULT_CURVE_VALUES, night_kelvin_transition: 1440 }},
].map((v) => {{
  const points = buildPoints(0, boundaries, v);
  const b = points.map((p) => p.brightness);
  return {{
    length: points.length,
    finite: points.every((p) => Number.isFinite(p.brightness) && Number.isFinite(p.kelvin)),
    varies: Math.min(...b) < Math.max(...b),
  }};
}});"""
    )
    assert result == [{"length": 289, "finite": True, "varies": True}] * 3


def test_curve_card_matches_curve_py():
    phase_cases = [
        {"t": float(t), "b": b}
        for b in MARK_CASES
        for t in list(range(0, 86400, 900)) + [x for edge in b for x in (edge - 1, edge, edge + 1)]
    ]
    js = run_js(
        f"""
const {{ phaseAt, phaseMarks, kelvinToRgb }} = await import({CARD_JS});
return {{
  phases: input.phaseCases.map((c) => phaseAt(c.t, ...c.b)),
  marks: input.markCases.map((b) => phaseMarks(...b)),
  rgb: input.kelvins.map(kelvinToRgb),
}};""",
        {"phaseCases": phase_cases, "markCases": MARK_CASES, "kelvins": KELVINS},
    )
    phase_mismatches = [
        f"t={c['t']} {c['b']}: py={phase_at(c['t'], *c['b'])} js={got}"
        for c, got in zip(phase_cases, js["phases"])
        if phase_at(c["t"], *c["b"]) != got
    ]
    assert not phase_mismatches, "\n".join(phase_mismatches[:10])
    for boundaries, got in zip(MARK_CASES, js["marks"]):
        assert [[n, s] for n, s in phase_marks(*boundaries)] == got, boundaries
    assert not _rgb_mismatches(js["rgb"]), "\n".join(_rgb_mismatches(js["rgb"])[:10])
