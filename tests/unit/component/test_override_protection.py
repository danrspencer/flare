from datetime import datetime, timedelta, timezone

import pytest
from homeassistant.core import Context, State

from custom_components.flare.schedule.curve import kelvin_to_rgb
from custom_components.flare.zone.override_protection import (
    _color_temp_matches,
    _context_matches,
    classify,
    classify_state,
    is_blocked,
    target_matches_values,
)

ON_TARGET = {"brightness": 200, "color_temp_kelvin": 3000}


def _claim(context_id, target=None, secondary=None):
    return {"context_id": context_id, "secondary_context_id": secondary, "target": target}


class TestClassifyByContext:
    @pytest.mark.parametrize(
        ("observed", "latest", "live", "expected"),
        [
            (None, None, "ctx-x", ("untracked", None)),
            # A dropped first-ever write looks like this, until an observed exists.
            (None, _claim("ctx-first"), "ctx-before", ("untracked", None)),
            (_claim("ctx-o"), _claim("ctx-l"), "ctx-l", ("controlled", "latest-context")),
            (_claim("ctx-o"), _claim("ctx-l"), "ctx-o", ("controlled", "observed-context")),
            # A two-step write's brightness step lands under its own context.
            (_claim("ctx-o"), _claim("ctx-l", secondary="ctx-l-step"), "ctx-l-step", ("controlled", "latest-context")),
            (_claim("ctx-o", secondary="ctx-o-step"), _claim("ctx-l"), "ctx-o-step", ("controlled", "observed-context")),
            (_claim("ctx-o"), None, "ctx-someone-else", ("overridden", None)),
        ],
        ids=[
            "no claim",
            "only an unverified latest",
            "latest",
            "observed",
            "latest secondary",
            "observed secondary",
            "neither",
        ],
    )
    def test_an_on_light(self, observed, latest, live, expected):
        assert classify(is_on=True, observed=observed, latest=latest, current_context=live) == expected

    def test_a_missing_secondary_never_matches_a_missing_live_context(self):
        assert not _context_matches(_claim("ctx-a"), None)
        assert not _context_matches({"context_id": "ctx-a"}, None)


class TestClassifyByValue:
    """HA forgets a write's context after 5s, so a slow device echoes our
    write under a new one. Values rescue that."""

    @pytest.mark.parametrize(
        ("observed_target", "latest_target", "live", "expected"),
        [
            (None, ON_TARGET, (200, 3000), ("controlled", "latest-value")),
            ({"brightness": 50, "color_temp_kelvin": 2700}, {"brightness": 10, "color_temp_kelvin": 2000}, (50, 2700), ("controlled", "observed-value")),
            (ON_TARGET, ON_TARGET, (200, 3000), ("controlled", "latest-value")),
            ({"brightness": 50, "color_temp_kelvin": 2700}, ON_TARGET, (40, 6000), ("overridden", None)),
            (None, ON_TARGET, (40, 6000), ("overridden", None)),
            (None, None, (200, 3000), ("overridden", None)),
            (None, ON_TARGET, (190, 3000), ("overridden", None)),
            (None, {"state": "off"}, (200, 3000), ("overridden", None)),
        ],
        ids=[
            "matches latest's target",
            "matches observed's target",
            "latest is checked first",
            "neither target matches",
            "values differ",
            "no recorded target",
            "colour matches, brightness doesn't",
            "we turned it off, someone turned it on",
        ],
    )
    def test_an_on_light_under_an_unrelated_context(self, observed_target, latest_target, live, expected):
        status = classify(
            is_on=True,
            observed=_claim("ctx-o", observed_target),
            latest=_claim("ctx-l", latest_target, secondary="ctx-l-step"),
            current_context="ctx-unrelated",
            current_brightness=live[0],
            current_color_temp_kelvin=live[1],
        )
        assert status == expected

    def test_a_bulb_reporting_in_rgb_mode_matches_its_kelvin_claim(self):
        """HA reports color_temp_kelvin as None outside COLOR_TEMP mode."""
        claim = _claim("ctx-ours", {"brightness": 255, "color_temp_kelvin": 3000})
        status, _ = classify(
            is_on=True,
            observed=claim,
            latest=claim,
            current_context="ctx-unrelated",
            current_brightness=255,
            current_color_temp_kelvin=None,
            current_rgb_color=kelvin_to_rgb(3000),
        )
        assert status == "controlled"

    @pytest.mark.parametrize(
        ("reported", "expected"), [(4000, "controlled"), (2700, "overridden")], ids=["at its ceiling", "elsewhere"]
    )
    def test_a_bulb_parked_at_its_ceiling_matches_a_target_beyond_it(self, reported, expected):
        claim = _claim("ctx-ours", {"brightness": 255, "color_temp_kelvin": 6531})
        status, _ = classify(
            is_on=True,
            observed=claim,
            latest=claim,
            current_context="ctx-unrelated",
            current_brightness=255,
            current_color_temp_kelvin=reported,
            min_color_temp_kelvin=2700,
            max_color_temp_kelvin=4000,
        )
        assert status == expected


class TestClassifyAnOffLight:
    """Being switched off is an override like any other."""

    def test_switched_off_by_someone_else_is_overridden(self):
        claim = _claim("ctx-ours", ON_TARGET)
        assert classify(is_on=False, observed=claim, latest=claim, current_context="ctx-else")[0] == "overridden"

    def test_our_own_turn_off_stays_ours_after_its_context_expires(self):
        claim = _claim("ctx-our-off", {"state": "off"})
        assert classify(is_on=False, observed=claim, latest=claim, current_context="ctx-later") == (
            "controlled",
            "latest-value",
        )

    def test_an_off_we_saw_land_stays_ours_under_a_newer_unlanded_write(self):
        observed = _claim("ctx-our-off", {"state": "off"})
        latest = _claim("ctx-newer", ON_TARGET)
        assert classify(is_on=False, observed=observed, latest=latest, current_context="ctx-later") == (
            "controlled",
            "observed-value",
        )

    def test_with_no_claim_it_is_off(self):
        assert classify(is_on=False, observed=None, latest=None, current_context="ctx-x") == ("off", None)

    def test_with_only_an_unverified_write_it_is_untracked(self):
        status, _ = classify(is_on=False, observed=None, latest=_claim("ctx-ours", ON_TARGET), current_context="ctx-else")
        assert status == "untracked"


class TestIsBlocked:
    @pytest.mark.parametrize(
        ("status", "blocked"), [("overridden", True), ("controlled", False), ("untracked", False), ("off", False)]
    )
    def test_only_overridden_blocks(self, status, blocked):
        assert is_blocked(status) is blocked

    def test_force_bypasses(self):
        assert is_blocked("overridden", force=True) is False


class TestTargetMatchesValues:
    def test_rgb_targets_compare_per_channel(self):
        target = {"brightness": 200, "rgb_color": [255, 120, 10]}
        assert target_matches_values(target, 200, None, [255, 121, 9])
        assert not target_matches_values(target, 200, None, [10, 10, 10])
        assert not target_matches_values(target, 200, None, [255, 120, 10, 0])

    def test_no_target_never_matches(self):
        assert not target_matches_values(None, 200, 3000, None)
        assert not target_matches_values({}, 200, 3000, None)

    def test_a_mired_equivalent_kelvin_matches(self):
        """4373K floors to mired 228, which reads back as 4385K."""
        assert target_matches_values({"brightness": 255, "color_temp_kelvin": 4373}, 255, 4385, None)


class TestColorTempMatches:
    def test_within_kelvin_tolerance(self):
        assert _color_temp_matches(3005, 3000, tolerance_kelvin=10)
        assert not _color_temp_matches(3050, 3000, tolerance_kelvin=10)

    def test_same_mired_matches_beyond_tolerance(self):
        assert _color_temp_matches(4385, 4373, tolerance_kelvin=10)

    def test_a_different_mired_does_not(self):
        assert not _color_temp_matches(6000, 3000, tolerance_kelvin=10)


class TestClassifyState:
    RECORD = {"observed": _claim("ctx-o", ON_TARGET), "latest": None}

    @pytest.mark.parametrize("state", [None, State("light.a", "unavailable"), State("light.a", "unknown")])
    def test_an_unreachable_light_is_unavailable_whatever_its_claims(self, state):
        assert classify_state(state, self.RECORD) == ("unavailable", None)

    def test_a_reachable_light_is_judged_against_its_claims(self):
        state = State("light.a", "on", {"brightness": 40, "color_temp_kelvin": 6000}, context=Context(id="ctx-x"))
        assert classify_state(state, self.RECORD)[0] in ("mismatched", "overridden")
        assert classify_state(state, None) == ("untracked", None)

    def test_a_mismatch_is_only_an_override_once_it_has_lasted(self):
        """Mismatched until its mismatch_since is MISMATCH_GRACE old; before
        anything has noted it, it's mismatched too."""
        state = State("light.a", "on", {"brightness": 40, "color_temp_kelvin": 6000}, context=Context(id="ctx-x"))
        now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
        since = lambda seconds: {**self.RECORD, "mismatch_since": (now - timedelta(seconds=seconds)).isoformat()}

        assert classify_state(state, self.RECORD, now=now) == ("mismatched", None)
        assert classify_state(state, since(29), now=now) == ("mismatched", None)
        assert classify_state(state, since(30), now=now) == ("overridden", None)

    def test_mismatched_is_blocked_like_overridden(self):
        assert is_blocked("mismatched") and is_blocked("overridden")
        assert not is_blocked("mismatched", force=True)

    def test_it_reads_the_live_values_and_the_bulbs_range(self):
        # Parked at its advertised 4000K ceiling, so a 5000K target still matches.
        state = State(
            "light.a",
            "on",
            {"brightness": 200, "color_temp_kelvin": 4000, "max_color_temp_kelvin": 4000},
            context=Context(id="ctx-x"),
        )
        record = {"observed": _claim("ctx-o", {"brightness": 200, "color_temp_kelvin": 5000}), "latest": None}
        assert classify_state(state, record) == ("controlled", "observed-value")
