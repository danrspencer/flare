"""
Pure unit tests for override_protection.classify()/target_matches_values() -
the standalone decision logic behind the claims_check/claims_record
services and grouping.py's own EntityLookup.externally_set() (now a thin
adapter over classify(), see grouping.py's own docstring).

No EntityLookup, no fakes beyond plain values - classify() takes exactly
the confirmed/pending claim dicts and live values it needs, nothing else.

Requires a real Home Assistant install (override_protection.py imports
homeassistant.util.color directly - see its own module docstring for why
that's a deliberate exception to "no HA dependency", not an oversight).
"""

from custom_components.flare.override_protection import _color_temp_matches, _context_matches, classify, is_blocked, target_matches_values


ON_TARGET = {"brightness": 200, "color_temp_kelvin": 3000}
OFF_TARGET = {"state": "off"}


def test_being_switched_off_by_hand_is_an_override():
    """Turning a light off is a choice worth respecting, the same as
    dimming it. The claim asked for brightness; the light is off under
    a context that isn't ours, so somebody else turned it off."""
    claim = {"context_id": "ctx-ours", "target": ON_TARGET}
    status, _via = classify(
        is_on=False, observed=claim, latest=claim, current_context="ctx-someone-else"
    )
    assert status == "overridden"
    assert is_blocked(status)


def test_our_own_turn_off_stays_ours_after_its_context_expires():
    """The counterpart, and the reason a turn-off records a target of
    its own: without one there is nothing to distinguish our off from
    anyone else's once HA's 5s context window closes, and a room turned
    off at bedtime could never be turned on again."""
    claim = {"context_id": "ctx-our-off", "target": OFF_TARGET}
    status, matched_via = classify(
        is_on=False, observed=claim, latest=claim, current_context="ctx-unrelated-later"
    )
    assert (status, matched_via) == ("controlled", "latest-value")
    assert not is_blocked(status)


def test_an_off_light_we_never_wrote_is_free():
    """No claim at all means no opinion to respect."""
    status, matched_via = classify(
        is_on=False, observed=None, latest=None, current_context="ctx-anything"
    )
    assert (status, matched_via) == ("off", None)
    assert not is_blocked("off")


def test_an_off_light_with_only_an_unverified_write_is_free():
    """One unconfirmed write isn't evidence anyone else did anything -
    the same reasoning as the on-light case below."""
    latest = {"context_id": "ctx-ours", "target": ON_TARGET}
    status, _via = classify(
        is_on=False, observed=None, latest=latest, current_context="ctx-someone-else"
    )
    assert status == "untracked"
    assert not is_blocked(status)


def test_no_claim_at_all_is_untracked():
    status, matched_via = classify(is_on=True, observed=None, latest=None, current_context="ctx-anything")
    assert (status, matched_via) == ("untracked", None)


def test_a_single_unverified_latest_that_does_not_match_is_untracked():
    # The one gap the two-claim design doesn't close: a light's very
    # first tracked write, if dropped, is indistinguishable from a
    # genuinely external change until a confirmed baseline exists.
    status, matched_via = classify(
        is_on=True,
        observed=None,
        latest={"context_id": "ctx-first-attempt"},
        current_context="ctx-whatever-this-light-had-before",
    )
    assert (status, matched_via) == ("untracked", None)


def test_context_matches_latest():
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest={"context_id": "ctx-latest"},
        current_context="ctx-latest",
    )
    assert (status, matched_via) == ("controlled", "latest-context")


def test_context_matches_observed():
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest={"context_id": "ctx-latest"},
        current_context="ctx-observed",
    )
    assert (status, matched_via) == ("controlled", "observed-context")


def test_context_matches_latests_secondary_context():
    # A two-step transition's brightness-only step lands under its own
    # context (see __init__.py's _two_step_turn_on) - matching that
    # secondary context is just as much "ours" as matching the primary
    # (colour step's) one.
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest={"context_id": "ctx-latest-colour", "secondary_context_id": "ctx-latest-brightness"},
        current_context="ctx-latest-brightness",
    )
    assert (status, matched_via) == ("controlled", "latest-context")


def test_context_matches_observeds_secondary_context():
    # confirmed inherits secondary_context_id automatically once
    # promoted (async_record just carries the whole old pending dict
    # forward) - this proves classify() actually checks it there too,
    # not just on pending.
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed-colour", "secondary_context_id": "ctx-observed-brightness"},
        latest={"context_id": "ctx-latest"},
        current_context="ctx-observed-brightness",
    )
    assert (status, matched_via) == ("controlled", "observed-context")


def test_secondary_context_absent_does_not_accidentally_match_none():
    # A claim with no secondary_context_id at all (the ordinary,
    # combined-write case) must never match on a live context that's
    # itself None (e.g. a brand new entity with no live state yet) -
    # _context_matches must not treat "no secondary" and "no live
    # context" as equal.
    assert not _context_matches({"context_id": "ctx-a", "secondary_context_id": None}, None)
    assert not _context_matches({"context_id": "ctx-a"}, None)


def test_context_matching_neither_primary_nor_secondary_falls_through_to_value_rescue():
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest={
            "context_id": "ctx-latest-colour",
            "secondary_context_id": "ctx-latest-brightness",
            "target": {"brightness": 200, "color_temp_kelvin": 3000},
        },
        current_context="ctx-completely-unrelated",
        current_brightness=200,
        current_color_temp_kelvin=3000,
    )
    assert (status, matched_via) == ("controlled", "latest-value")


def test_context_matches_neither_but_value_matches_latests_target():
    # The delayed-echo rescue - see classify()'s own docstring for why
    # a context mismatch alone doesn't prove an external touch.
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest={"context_id": "ctx-latest", "target": {"brightness": 200, "color_temp_kelvin": 3000}},
        current_context="ctx-device-echo-unrelated",
        current_brightness=200,
        current_color_temp_kelvin=3000,
    )
    # Rescued back to "controlled" on value alone. matched_via
    # distinguishes this from the context-matched "controlled" case
    # above.
    assert (status, matched_via) == ("controlled", "latest-value")


def test_context_matches_neither_but_value_matches_observeds_own_target():
    # The other half of the value-rescue, checking both claims was
    # always the point of keeping two - a light that genuinely hasn't
    # updated at all yet is, by definition, still showing exactly what
    # `confirmed` itself asked for; its live context just happens to
    # have changed for some unrelated reason (a benign registry event,
    # a two-step bulb's other step landing under its own context, etc).
    # pending's own target (10/2000) deliberately does NOT match, so
    # this only passes if confirmed's target is actually being checked.
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed", "target": {"brightness": 50, "color_temp_kelvin": 2700}},
        latest={"context_id": "ctx-latest", "target": {"brightness": 10, "color_temp_kelvin": 2000}},
        current_context="ctx-something-unrelated",
        current_brightness=50,
        current_color_temp_kelvin=2700,
    )
    assert (status, matched_via) == ("controlled", "observed-value")


def test_latest_value_rescue_is_checked_before_observeds():
    # When both would technically match, pending (the more recent claim)
    # takes precedence - matching classify()'s existing context-check
    # ordering (pending before confirmed).
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed", "target": {"brightness": 200, "color_temp_kelvin": 3000}},
        latest={"context_id": "ctx-latest", "target": {"brightness": 200, "color_temp_kelvin": 3000}},
        current_context="ctx-something-unrelated",
        current_brightness=200,
        current_color_temp_kelvin=3000,
    )
    assert (status, matched_via) == ("controlled", "latest-value")


def test_rescue_does_not_apply_when_neither_claims_target_matches():
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed", "target": {"brightness": 50, "color_temp_kelvin": 2700}},
        latest={"context_id": "ctx-latest", "target": {"brightness": 200, "color_temp_kelvin": 3000}},
        current_context="ctx-someone-else",
        current_brightness=40,
        current_color_temp_kelvin=6000,
    )
    assert (status, matched_via) == ("overridden", None)


def test_rescue_does_not_apply_when_values_dont_match():
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest={"context_id": "ctx-latest", "target": {"brightness": 200, "color_temp_kelvin": 3000}},
        current_context="ctx-someone-else",
        current_brightness=40,
        current_color_temp_kelvin=6000,
    )
    assert (status, matched_via) == ("overridden", None)


def test_rescue_does_not_apply_when_latest_has_no_recorded_target():
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest={"context_id": "ctx-latest", "target": None},
        current_context="ctx-someone-else",
        current_brightness=200,
        current_color_temp_kelvin=3000,
    )
    assert (status, matched_via) == ("overridden", None)


def test_genuinely_overridden_when_observed_exists_and_nothing_matches():
    status, matched_via = classify(
        is_on=True,
        observed={"context_id": "ctx-observed"},
        latest=None,
        current_context="ctx-someone-else",
    )
    assert (status, matched_via) == ("overridden", None)


def test_target_matches_values_rgb_variant():
    assert target_matches_values(
        {"brightness": 200, "rgb_color": [255, 120, 10]},
        current_brightness=200,
        current_color_temp_kelvin=None,
        current_rgb_color=[255, 121, 9],
    )
    assert not target_matches_values(
        {"brightness": 200, "rgb_color": [255, 120, 10]},
        current_brightness=200,
        current_color_temp_kelvin=None,
        current_rgb_color=[10, 10, 10],
    )


def test_target_matches_values_no_target_never_matches():
    assert not target_matches_values(None, 200, 3000, None)
    assert not target_matches_values({}, 200, 3000, None)


def test_target_matches_values_recognises_a_mired_equivalent_color_temp():
    # The live incident this fix closes: 4373K asked for, 4385K reported
    # back - both floor to mired 228 via HA's own
    # color_temperature_kelvin_to_mired, so they're the same colour as
    # far as the device is concerned, even though the Kelvin gap (12)
    # exceeds the default color_temp_tolerance (10).
    assert target_matches_values(
        {"brightness": 255, "color_temp_kelvin": 4373},
        current_brightness=255,
        current_color_temp_kelvin=4385,
        current_rgb_color=None,
    )


def test_is_blocked_force_bypasses_regardless_of_status():
    assert is_blocked("overridden", force=True) is False


def test_is_blocked_off_and_untracked_never_block():
    assert is_blocked("off") is False
    assert is_blocked("untracked") is False


def test_is_blocked_overridden_always_blocks():
    assert is_blocked("overridden") is True


def test_is_blocked_controlled_never_blocks():
    """There is no owner comparison to make. Which scope a claim lives
    under is the caller's own choice (see write_tracking.py), so a
    `controlled` claim is by construction the claim of whatever scope
    the caller named - two callers naming the same scope share it."""
    assert is_blocked("controlled") is False


def test_color_temp_matches_within_flat_kelvin_tolerance():
    # The pre-existing behaviour, unchanged: close enough in plain
    # Kelvin terms matches regardless of mireds.
    assert _color_temp_matches(3005, 3000, tolerance_kelvin=10)
    assert not _color_temp_matches(3050, 3000, tolerance_kelvin=10)


def test_color_temp_matches_the_real_live_incident_exactly():
    # 4373K -> floor(1000000/4373) = mired 228 -> floor(1000000/228) = 4385K.
    # Confirmed live: HA's own conversion, not a guess.
    assert _color_temp_matches(4385, 4373, tolerance_kelvin=10)


def test_color_temp_matches_rejects_a_genuinely_different_mired_value():
    # A gap large enough that it's not explained by mired rounding at
    # all - e.g. brightness 40/color 6000 vs target 3000 from the
    # override tests above. Neither within tolerance nor mired-equal.
    assert not _color_temp_matches(6000, 3000, tolerance_kelvin=10)


# Regression tests below, for the bathroom-spots incident (2026-09-14):
# four light.bathroom_spot_1-4 were released ("found this light showing
# something else") at 08:28:23, after ~89 minutes unavailable and a
# device-originated attribute report at 08:28:15. Both pin a cause fixed
# in classify()/target_matches_values() - see override_protection.py's
# _color_temp_matches_rgb and _clamp_kelvin.


def test_a_colour_reported_in_a_different_mode_is_recognised_as_a_match():
    """Cause 1: FLARE's claim asked for a colour in Kelvin, but the bulbs
    were in xy colour mode by the time they echoed back - and Home
    Assistant's own LightEntity.state_attributes reports
    color_temp_kelvin as exactly None whenever color_mode isn't
    COLOR_TEMP (homeassistant/components/light/__init__.py). Before the
    fix, classify()'s value-rescue only ever read
    current_color_temp_kelvin for a colour-temp claim, so it never
    looked at the rgb_color the device actually reported, no matter how
    close.

    current_rgb_color below isn't a guess at "close enough" - it is
    exactly curve.kelvin_to_rgb(3000), FLARE's own Kelvin->RGB
    conversion, so this is provably the identical colour by FLARE's own
    definition, just reported through a different attribute.
    """
    from custom_components.flare.curve import kelvin_to_rgb

    claim = {"context_id": "ctx-ours", "target": {"brightness": 255, "color_temp_kelvin": 3000}}
    status, _via = classify(
        is_on=True,
        observed=claim,
        latest=claim,
        current_context="ctx-device-attribute-report",
        current_brightness=255,
        current_color_temp_kelvin=None,  # what HA reports once color_mode is xy, not color_temp
        current_rgb_color=kelvin_to_rgb(3000),
    )
    assert status == "controlled", (
        "a device reporting the identical colour via rgb_color rather than color_temp_kelvin "
        "should still match, not read as overridden"
    )


def test_a_bulb_sitting_at_its_own_colour_temp_ceiling_is_recognised_as_a_match():
    """Cause 2: the curve asked for 6531K (a real Morning-phase value),
    but these IKEA TRADFRI GU10s advertise max_color_temp_kelvin 4000 -
    so the bulb settles at its own ceiling and can never echo back
    6531K, no matter how long it's given.

    grouping.py's _already_set() already handled exactly this for the
    "does this still need writing" check - clamp_color_temp_kelvin()
    narrows the target to the entity's own advertised range before
    comparing (see its own docstring: "a bulb that physically can't reach
    the target settles at its ceiling and would otherwise never compare
    equal"). Before the fix, classify()/target_matches_values() had no
    equivalent: it was a pure function with no entity_id/lookup at all,
    so it could never learn a bulb's ceiling and always compared against
    the raw, un-clamped target - a standing false-positive for any light
    whose curve target exceeds what it can physically produce, not a
    one-off. max_color_temp_kelvin below is exactly what a real caller
    (grouping.EntityLookup.externally_set) now reads off the entity and
    passes through.
    """
    claim = {"context_id": "ctx-ours", "target": {"brightness": 255, "color_temp_kelvin": 6531}}
    status, _via = classify(
        is_on=True,
        observed=claim,
        latest=claim,
        current_context="ctx-device-attribute-report",
        current_brightness=255,
        current_color_temp_kelvin=4000,  # the bulb's own advertised ceiling
        max_color_temp_kelvin=4000,
    )
    assert status == "controlled", (
        "a bulb sitting at its own advertised colour-temp ceiling should read as controlled, not overridden"
    )


def test_a_colour_temp_claim_beyond_the_bulbs_ceiling_still_overrides_on_a_genuine_mismatch():
    # The ceiling fallback must not swallow a real override: a bulb
    # reporting something other than its own ceiling (here, its floor)
    # is still overridden, not waved through just because a range was
    # supplied.
    claim = {"context_id": "ctx-ours", "target": {"brightness": 255, "color_temp_kelvin": 6531}}
    status, _via = classify(
        is_on=True,
        observed=claim,
        latest=claim,
        current_context="ctx-someone-else",
        current_brightness=255,
        current_color_temp_kelvin=2700,  # nowhere near either the target or its clamped ceiling
        min_color_temp_kelvin=2700,
        max_color_temp_kelvin=4000,
    )
    assert status == "overridden"
