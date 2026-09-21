"""
Pure-logic tests for two_step.py - no Home Assistant dependency, same
as test_curve.py/test_grouping.py/test_scenes.py (see tests/conftest.py
for how the module is imported bare).

The end-to-end half - a real device/entity registry, and grouping.py's
EntityLookup.matches_two_step_pattern() actually being reached by a real
apply_lighting/compute_lighting_groups call - lives in
tests/integration/test_services.py, since none of that can be exercised
without a real registry and a real Tracking config entry.
"""

from custom_components.flare.services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS, model_matches, parse_patterns


class TestModelMatching:
    def test_the_shipped_default_matches_a_real_tradfri_gu10(self):
        assert model_matches(
            "IKEA", "TRADFRI bulb GU10, color/white spectrum, 345 lm", DEFAULT_TWO_STEP_MODEL_PATTERNS
        )

    def test_matching_is_case_insensitive(self):
        """Manufacturer strings are wildly inconsistent between
        integrations for the same physical bulb."""
        assert model_matches("ikea", "tradfri BULB gu10", ["*TRADFRI bulb*"])

    def test_a_different_manufacturers_bulb_does_not_match(self):
        assert not model_matches("Signify Netherlands B.V.", "Hue color spot", DEFAULT_TWO_STEP_MODEL_PATTERNS)

    def test_a_pattern_can_pin_the_manufacturer_alone(self):
        assert model_matches("IKEA", "KAJPLATS bulb", ["ikea*"])

    def test_missing_manufacturer_and_model_never_matches(self):
        """A device with no identity at all mustn't match a bare '*'
        pattern into flagging every light in the house."""
        assert not model_matches(None, None, ["*"])

    def test_empty_pattern_list_matches_nothing(self):
        assert not model_matches("IKEA", "TRADFRI bulb GU10", [])


class TestParseExtraPatterns:
    def test_splits_on_newlines_and_strips(self):
        assert parse_patterns(" *foo*\n\n  *bar* \n") == ["*foo*", "*bar*"]

    def test_also_accepts_commas(self):
        assert parse_patterns("*foo*, *bar*") == ["*foo*", "*bar*"]

    def test_blank_and_none_yield_nothing(self):
        """A misconfigured options field should fall back to the shipped
        defaults, never raise during setup."""
        assert parse_patterns("") == []
        assert parse_patterns(None) == []
        assert parse_patterns("\n  \n") == []
