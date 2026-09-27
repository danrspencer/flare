"""two_step.py's pattern matching. Routing through real registries is in
functional/component/test_services.py."""

from custom_components.flare.services.two_step import DEFAULT_TWO_STEP_MODEL_PATTERNS, model_matches, parse_patterns


class TestModelMatching:
    def test_the_shipped_default_matches_a_real_tradfri_gu10(self):
        assert model_matches(
            "IKEA", "TRADFRI bulb GU10, color/white spectrum, 345 lm", DEFAULT_TWO_STEP_MODEL_PATTERNS
        )

    def test_matching_is_case_insensitive(self):
        assert model_matches("ikea", "tradfri BULB gu10", ["*TRADFRI bulb*"])

    def test_a_different_manufacturers_bulb_does_not_match(self):
        assert not model_matches("Signify Netherlands B.V.", "Hue color spot", DEFAULT_TWO_STEP_MODEL_PATTERNS)

    def test_a_pattern_can_pin_the_manufacturer_alone(self):
        assert model_matches("IKEA", "KAJPLATS bulb", ["ikea*"])

    def test_missing_manufacturer_and_model_never_matches(self):
        """Not even a bare '*'."""
        assert not model_matches(None, None, ["*"])

    def test_empty_pattern_list_matches_nothing(self):
        assert not model_matches("IKEA", "TRADFRI bulb GU10", [])


class TestParsePatterns:
    def test_splits_on_newlines_and_strips(self):
        assert parse_patterns(" *foo*\n\n  *bar* \n") == ["*foo*", "*bar*"]

    def test_also_accepts_commas(self):
        assert parse_patterns("*foo*, *bar*") == ["*foo*", "*bar*"]

    def test_blank_and_none_yield_nothing(self):
        assert parse_patterns("") == []
        assert parse_patterns(None) == []
        assert parse_patterns("\n  \n") == []
