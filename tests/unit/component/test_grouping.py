import pytest

from custom_components.flare.services.grouping import MAX_BRIGHTNESS, build_groups
from tests.support.fakes import make_lookup

TRADFRI = ("IKEA", "TRADFRI bulb GU10, color/white spectrum, 345 lm")
HUE = ("Signify", "Hue color spot")
WARM_RGB = (255, 180, 107)


def _on(brightness=None, kelvin=None, context_id=None, **attributes):
    if brightness is not None:
        attributes["brightness"] = brightness
    if kelvin is not None:
        attributes["color_temp_kelvin"] = kelvin
    return {"state": "on", "attributes": attributes, "context_id": context_id}


def _off(**attributes):
    return {"state": "off", "attributes": attributes}


def _groups(states, *, brightness=200, kelvin=3000, multipliers=None, lookup_kwargs=None, **kwargs):
    """build_groups over every entity in `states`."""
    return build_groups(
        entities=list(states),
        brightness_multipliers=multipliers or {},
        sensor_brightness=brightness,
        sensor_color_temp_kelvin=kelvin,
        lookup=make_lookup(states, **(lookup_kwargs or {})),
        **kwargs,
    )


def test_unreachable_entities_are_in_no_group():
    groups = _groups(
        {
            "light.a": _on(100),
            "light.b": {"state": "unavailable", "attributes": {}},
            "light.c": {"state": "unknown", "attributes": {}},
        }
    )
    assert len(groups) == 1
    assert groups[0].combined + groups[0].two_step + groups[0].needing_off == ["light.a"]


class TestTolerance:
    def test_a_light_already_at_target_is_skipped(self):
        groups = _groups({"light.a": _on(180, 3050)}, brightness=180, kelvin=3050)
        assert groups[0].combined == []

    def test_within_tolerance_is_at_target(self):
        """Default tolerance: brightness ±2, Kelvin ±10, both inclusive."""
        assert _groups({"light.a": _on(198, 3010)})[0].combined == []
        assert _groups({"light.a": _on(197, 3000)})[0].combined == ["light.a"]
        assert _groups({"light.a": _on(200, 3011)})[0].combined == ["light.a"]

    def test_a_mired_equivalent_colour_temperature_is_at_target(self):
        """4373K and 4385K are 12K apart but floor to the same mired."""
        assert _groups({"light.a": _on(255, 4385)}, brightness=255, kelvin=4373)[0].combined == []

    def test_rgb_is_compared_per_channel(self):
        close = _on(200, supported_color_modes=["rgb"], rgb_color=[253, 181, 108])
        far = _on(200, supported_color_modes=["rgb"], rgb_color=[255, 180, 90])
        assert _groups({"light.a": close}, prefer_rgb_color=True, rgb_color=WARM_RGB)[0].combined_rgb == []
        assert _groups({"light.a": far}, prefer_rgb_color=True, rgb_color=WARM_RGB)[0].combined_rgb == ["light.a"]


# Kelvin targets match the raw target OR the target clamped to the bulb's
# advertised range, never only the clamped one: some bulbs sit at a ceiling
# below the target, and some report outside their own advertised range.
_COLOUR_RANGE_CASES = [
    ("at its ceiling, target above it", 255, 6535, 2000, 6535, 255, 6667, []),
    ("at its floor, target below it", 80, 2202, 2202, 4000, 80, 1708, []),
    ("reachable target it hasn't met yet", 255, 6535, 2000, 6535, 255, 4000, ["light.a"]),
    ("publishes no range at all", 255, 6535, None, None, 255, 6667, ["light.a"]),
    ("reports outside its advertised range", 255, 5813, 2202, 4000, 255, 5813, []),
]


@pytest.mark.parametrize(
    ("brightness", "current_kelvin", "min_kelvin", "max_kelvin", "target_brightness", "target_kelvin", "expected"),
    [case[1:] for case in _COLOUR_RANGE_CASES],
    ids=[case[0] for case in _COLOUR_RANGE_CASES],
)
def test_colour_target_is_compared_against_the_raw_and_range_clamped_value(
    brightness, current_kelvin, min_kelvin, max_kelvin, target_brightness, target_kelvin, expected
):
    attributes = {}
    if min_kelvin is not None:
        attributes = {"min_color_temp_kelvin": min_kelvin, "max_color_temp_kelvin": max_kelvin}
    groups = _groups(
        {"light.a": _on(brightness, current_kelvin, **attributes)}, brightness=target_brightness, kelvin=target_kelvin
    )
    assert groups[0].combined == expected


class TestMultipliers:
    def test_zero_turns_off_only_lights_that_are_on(self):
        groups = _groups(
            {"light.a": _on(), "light.b": _off()}, multipliers={"light.a": 0, "light.b": 0}
        )
        assert len(groups) == 1
        assert groups[0].brightness == 0
        assert groups[0].needing_off == ["light.a"]

    @pytest.mark.parametrize("hands_off", [None, False])
    def test_null_or_false_leaves_the_light_out_entirely(self, hands_off):
        assert _groups({"light.a": _off()}, multipliers={"light.a": hands_off}) == []

    def test_distinct_multipliers_form_separate_groups(self):
        groups = _groups({"light.a": _off(), "light.b": _off()}, multipliers={"light.a": 1, "light.b": 0.1})
        by_multiplier = {g.multiplier: g for g in groups}
        assert (by_multiplier[1].brightness, by_multiplier[1].combined) == (200, ["light.a"])
        assert (by_multiplier[0.1].brightness, by_multiplier[0.1].combined) == (20, ["light.b"])

    @pytest.mark.parametrize(
        ("multiplier", "sensor_brightness", "expected"),
        [(0.001, 10, 1), (1.5, 200, MAX_BRIGHTNESS), (0.5, 200, 100)],
        ids=["floors at 1, not off", "caps at MAX_BRIGHTNESS", "scales in between"],
    )
    def test_arithmetic(self, multiplier, sensor_brightness, expected):
        groups = _groups({"light.a": _off()}, brightness=sensor_brightness, multipliers={"light.a": multiplier})
        assert groups[0].brightness == expected

    def test_a_light_at_max_is_not_recommanded_when_the_multiplier_overshoots(self):
        """light.turn_on clamps to 255, so an unclamped 300 target would
        never read as reached."""
        groups = _groups({"light.a": _on(255, 3000)}, multipliers={"light.a": 1.5})
        assert groups[0].combined == []


class TestTwoStepRouting:
    """A light goes two-step if it carries the label OR its model matches a
    pattern."""

    def test_by_label(self):
        groups = _groups(
            {"light.a": _on(180, 3050), "light.b": _off(), "light.c": {"state": "unavailable", "attributes": {}}},
            lookup_kwargs=dict(device_of={"light.a": "dev1", "light.b": "dev2"}, labels_of={"dev1": ["no_combined_transition"]}),
        )
        assert (groups[0].two_step, groups[0].combined, groups[0].needing_off) == (["light.a"], ["light.b"], [])

    @pytest.mark.parametrize(
        ("identity", "labels", "two_step"),
        [(TRADFRI, [], True), (HUE, ["no_combined_transition"], True), (HUE, [], False)],
        ids=["pattern match, no label", "label, no pattern match", "neither"],
    )
    @pytest.mark.parametrize("rgb", [False, True], ids=["colour temp", "rgb"])
    def test_by_pattern_or_label(self, identity, labels, two_step, rgb):
        light = _off(supported_color_modes=["rgb"]) if rgb else _on(180, 3050)
        groups = _groups(
            {"light.a": light},
            lookup_kwargs=dict(device_of={"light.a": "dev1"}, device_identity={"dev1": identity}, labels_of={"dev1": labels}),
            two_step_model_patterns=["*TRADFRI bulb*"],
            prefer_rgb_color=rgb,
            rgb_color=WARM_RGB if rgb else None,
        )
        routed, other = (groups[0].two_step_rgb, groups[0].combined_rgb) if rgb else (groups[0].two_step, groups[0].combined)
        assert (routed, other) == ((["light.a"], []) if two_step else ([], ["light.a"]))

    def test_no_patterns_matches_nothing(self):
        lookup = make_lookup(
            {"light.a": _on()}, device_of={"light.a": "dev1"}, device_identity={"dev1": TRADFRI}
        )
        assert lookup.matches_two_step_pattern("light.a", []) is False


class TestRgbRouting:
    def test_supports_rgb_reads_supported_color_modes(self):
        lookup = make_lookup(
            {
                "light.rgb": _on(supported_color_modes=["rgb", "color_temp"]),
                "light.xy": _on(supported_color_modes=["xy"]),
                "light.temp_only": _on(supported_color_modes=["color_temp"]),
                "light.brightness_only": _on(supported_color_modes=["brightness"]),
                "light.no_attr": _on(),
            }
        )
        assert [lookup.supports_rgb(e) for e in ("light.rgb", "light.xy", "light.temp_only", "light.brightness_only", "light.no_attr")] == [
            True,
            True,
            False,
            False,
            False,
        ]

    STATES = {"light.rgb": _off(supported_color_modes=["rgb"]), "light.temp": _off(supported_color_modes=["color_temp"])}

    def test_prefer_rgb_routes_only_rgb_capable_lights(self):
        groups = _groups(self.STATES, prefer_rgb_color=True, rgb_color=WARM_RGB)
        assert (groups[0].combined_rgb, groups[0].combined) == (["light.rgb"], ["light.temp"])

    @pytest.mark.parametrize(("prefer", "rgb_color"), [(False, WARM_RGB), (True, None)], ids=["toggle off", "no rgb_color"])
    def test_without_both_toggle_and_colour_everything_is_colour_temp(self, prefer, rgb_color):
        groups = _groups(self.STATES, prefer_rgb_color=prefer, rgb_color=rgb_color)
        assert sorted(groups[0].combined) == ["light.rgb", "light.temp"]
        assert groups[0].combined_rgb == groups[0].two_step_rgb == []


# --- Override protection -------------------------------------------------
#
# The decision table is override_protection.classify(), tested in
# test_override_protection.py. What's tested here is the adapter:
# externally_set() passing every claim field through, and build_groups()
# dropping an excluded light from every bucket.


def _overridden(**attributes):
    return _on(context_id="ctx-someone-else", **attributes)


OURS = dict(observed_context_ids={"light.a": "ctx-ours"})


class TestOverrideProtection:
    def test_an_overridden_light_is_left_out_of_the_update_group(self):
        groups = _groups({"light.a": _overridden(brightness=40, color_temp_kelvin=6000)}, lookup_kwargs=OURS)
        assert groups[0].combined == []

    def test_an_overridden_light_is_left_out_of_the_off_group(self):
        groups = _groups({"light.a": _overridden()}, multipliers={"light.a": 0}, lookup_kwargs=OURS)
        assert groups[0].needing_off == []

    def test_an_overridden_rgb_light_is_left_out_too(self):
        groups = _groups(
            {"light.a": _overridden(brightness=10, supported_color_modes=["rgb"])},
            lookup_kwargs=OURS,
            prefer_rgb_color=True,
            rgb_color=WARM_RGB,
        )
        assert groups[0].combined_rgb == groups[0].two_step_rgb == []

    def test_force_writes_anyway(self):
        groups = _groups({"light.a": _overridden(brightness=40, color_temp_kelvin=6000)}, lookup_kwargs=OURS, force=True)
        assert groups[0].combined == ["light.a"]

    # Each case flips if its field never reaches classify(). The light sits
    # at 200/3000 against a 100/5000 target, so it needs a write unless
    # override protection excludes it.
    _CLAIM_FIELD_CASES = [
        (
            "observed.target",
            dict(observed_context_ids={"light.a": "ctx-c"}, observed_targets={"light.a": {"brightness": 200, "color_temp_kelvin": 3000}}),
            "ctx-unrelated",
        ),
        (
            "latest.target",
            dict(
                observed_context_ids={"light.a": "ctx-c"},
                latest_context_ids={"light.a": "ctx-p"},
                latest_targets={"light.a": {"brightness": 200, "color_temp_kelvin": 3000}},
            ),
            "ctx-unrelated",
        ),
        (
            "observed.secondary_context_id",
            dict(observed_context_ids={"light.a": "ctx-c"}, observed_secondary_context_ids={"light.a": "ctx-c-step"}),
            "ctx-c-step",
        ),
        (
            "latest.secondary_context_id",
            dict(
                observed_context_ids={"light.a": "ctx-c"},
                latest_context_ids={"light.a": "ctx-p"},
                latest_secondary_context_ids={"light.a": "ctx-p-step"},
            ),
            "ctx-p-step",
        ),
    ]

    @pytest.mark.parametrize(
        ("claims", "live_context"), [c[1:] for c in _CLAIM_FIELD_CASES], ids=[c[0] for c in _CLAIM_FIELD_CASES]
    )
    def test_every_claim_field_reaches_classify(self, claims, live_context):
        groups = _groups({"light.a": _on(200, 3000, context_id=live_context)}, brightness=100, kelvin=5000, lookup_kwargs=claims)
        assert groups[0].combined == ["light.a"]

    def test_the_bulbs_colour_range_reaches_classify(self):
        """A bulb parked at its ceiling still matches a claim that asked
        for more than it can reach."""
        groups = _groups(
            {"light.a": _on(255, 6535, context_id="ctx-unrelated", min_color_temp_kelvin=2000, max_color_temp_kelvin=6535)},
            brightness=255,
            kelvin=4000,
            lookup_kwargs=dict(
                observed_context_ids={"light.a": "ctx-c"},
                observed_targets={"light.a": {"brightness": 255, "color_temp_kelvin": 6667}},
            ),
        )
        assert groups[0].combined == ["light.a"]

    def test_a_value_match_stops_protecting_once_the_curve_moves_on(self):
        """The value rescue isn't a permanent pass: a light still on the
        recorded target needs a write once the target changes."""
        groups = _groups(
            {"light.a": _on(200, 3000, context_id="ctx-unrelated")},
            brightness=120,
            kelvin=4200,
            lookup_kwargs=dict(
                observed_context_ids={"light.a": "ctx-c"},
                latest_context_ids={"light.a": "ctx-p"},
                latest_targets={"light.a": {"brightness": 200, "color_temp_kelvin": 3000}},
            ),
        )
        assert groups[0].combined == ["light.a"]
