import pytest

from custom_components.flare.schedule.curve import (
    brightness_for_phase,
    kelvin_for_phase,
    kelvin_to_rgb,
    phase_at,
    phase_marks,
    targets_for_phase,
)

# A synthetic day, in seconds: 06:00 morning, 08:00 day, 18:00 evening,
# 22:00 night.
_H = 3600
MORNING = 6 * _H
DAY_START = 8 * _H
EVENING = 18 * _H
NIGHT = 22 * _H

# The shipped defaults, (brightness, kelvin) at the start of each phase.
DEFAULTS = {"Morning": (255, 6667), "Day": (255, 6667), "Evening": (180, 3200), "Night": (80, 2700)}
PHASE_STARTS = [("Morning", MORNING), ("Day", DAY_START), ("Evening", EVENING), ("Night", NIGHT)]


def _bri(phase, t, **kw):
    return brightness_for_phase(phase, t, MORNING, DAY_START, EVENING, NIGHT, **kw)


def _kel(phase, t, **kw):
    return kelvin_for_phase(phase, t, MORNING, DAY_START, EVENING, NIGHT, **kw)


def _targets(phase, t, **kw):
    return targets_for_phase(phase, t, EVENING, DAY_START, NIGHT, MORNING, **kw)


def test_phase_at_boundaries():
    assert phase_at(0, MORNING, DAY_START, EVENING, NIGHT) == "Night"
    assert phase_at(MORNING, MORNING, DAY_START, EVENING, NIGHT) == "Morning"
    assert phase_at(DAY_START, MORNING, DAY_START, EVENING, NIGHT) == "Day"
    assert phase_at(EVENING, MORNING, DAY_START, EVENING, NIGHT) == "Evening"
    assert phase_at(NIGHT, MORNING, DAY_START, EVENING, NIGHT) == "Night"
    assert phase_at(NIGHT + _H, MORNING, DAY_START, EVENING, NIGHT) == "Night"


class TestDefaults:
    @pytest.mark.parametrize("phase,start", PHASE_STARTS)
    def test_every_phase_is_its_own_value_at_its_own_start(self, phase, start):
        """Transitions run *before* a boundary, so at 06:00 it IS the
        morning setting."""
        assert (_bri(phase, start), _kel(phase, start)) == DEFAULTS[phase]
        targets = _targets(phase, start)
        assert (targets["brightness"], targets["kelvin"]) == DEFAULTS[phase]

    def test_evening_fades_to_night_over_its_last_hour(self):
        fade_start = NIGHT - _H
        assert (_bri("Evening", fade_start - 1), _kel("Evening", fade_start - 1)) == (180, 3200)
        assert (_bri("Evening", fade_start), _kel("Evening", fade_start)) == (180, 3200)
        assert (_bri("Evening", fade_start + 1800), _kel("Evening", fade_start + 1800)) == (130, 2950)
        assert (_bri("Evening", NIGHT), _kel("Evening", NIGHT)) == (80, 2700)

    def test_day_slides_from_morning_colour_to_evening_colour_across_the_whole_phase(self):
        """Day's default colour transition is longer than any Day, so it
        clamps to the whole phase."""
        assert _kel("Day", DAY_START) == 6667
        assert _kel("Day", DAY_START + (EVENING - DAY_START) / 3) == 5511
        assert _kel("Day", EVENING) == 3200


class TestCustomValues:
    def test_each_brightness_is_its_own_knob(self):
        assert _bri("Morning", 0, morning_brightness=100) == 100
        assert _bri("Day", 0, morning_brightness=100) == 255
        assert _bri("Day", 0, day_brightness=200) == 200
        assert _bri("Morning", 0, day_brightness=200) == 255
        assert _bri("Night", 0, night_brightness=50) == 50
        assert _bri("Evening", NIGHT - _H - 1, evening_brightness=150) == 150

    def test_each_kelvin_is_its_own_knob(self):
        assert _kel("Morning", 0, morning_kelvin=5000) == 5000
        assert _kel("Day", DAY_START, morning_kelvin=5000) == 6667
        assert _kel("Day", DAY_START, day_kelvin=3500) == 3500
        assert _kel("Evening", EVENING, evening_kelvin=3000) == 3000

    def test_night_kelvin_moves_night_and_the_end_of_evenings_fade_only(self):
        assert _kel("Night", 0, night_kelvin=2000) == 2000
        assert _kel("Evening", NIGHT, night_kelvin=2000) == 2000
        assert _kel("Evening", NIGHT - _H, night_kelvin=2000) == 3200
        assert _kel("Evening", EVENING, night_kelvin=2000) == 3200
        assert _kel("Morning", 0, night_kelvin=2000) == 6667
        assert _kel("Day", DAY_START, night_kelvin=2000) == 6667

    def test_targets_pass_curve_values_through(self):
        assert _targets("Morning", 0, morning_brightness=120)["brightness"] == 120


class TestTransitions:
    """Each phase holds its value, then eases to the next phase's over the
    last N minutes of its own span."""

    def test_a_zero_duration_is_a_hard_cut(self):
        assert _kel("Evening", NIGHT - 1, evening_kelvin_transition=0) == 3200
        assert _kel("Night", NIGHT, evening_kelvin_transition=0) == 2700
        assert _bri("Evening", NIGHT - 1, evening_brightness_transition=0) == 180
        assert _bri("Night", NIGHT, night_brightness_transition=0) == 80

    def test_a_duration_longer_than_its_phase_covers_the_whole_phase(self):
        """And never bleeds back into the phase before."""
        # Evening is four hours here; a six-hour transition can only use four.
        assert _kel("Evening", EVENING, evening_kelvin_transition=360) == 3200
        quarter = EVENING + (NIGHT - EVENING) / 4
        assert _kel("Evening", quarter, evening_kelvin_transition=360) == _kel(
            "Evening", quarter, evening_kelvin_transition=240
        )

    def test_brightness_and_colour_transition_independently(self):
        t = NIGHT - 1800
        both = _targets("Evening", t)
        assert (both["brightness"], both["kelvin"]) == (130, 2950)
        colour_off = _targets("Evening", t, evening_kelvin_transition=0)
        assert (colour_off["brightness"], colour_off["kelvin"]) == (130, 3200)
        brightness_off = _targets("Evening", t, evening_brightness_transition=0)
        assert (brightness_off["brightness"], brightness_off["kelvin"]) == (180, 2950)

    def test_nights_transition_runs_before_morning_not_before_midnight(self):
        """Night spans midnight; its handover is to Morning."""
        assert _kel("Night", MORNING - 1800, night_kelvin_transition=30) == 2700
        assert _kel("Night", MORNING - 900, night_kelvin_transition=30) == 4684
        assert _kel("Night", MORNING, night_kelvin_transition=30) == 6667
        assert _kel("Night", NIGHT + _H, night_kelvin_transition=30) == 2700


class TestOverriddenPhase:
    """A phase override is asked for at the real time, which can be outside
    that phase's own span. It must show the phase's own values - not an
    extrapolation, and not the next phase's."""

    def test_past_its_own_end(self):
        # Unclamped, Evening's fade would extrapolate to ~2200K and ~1708K here.
        assert _kel("Evening", NIGHT + _H) == 3200
        assert _kel("Evening", NIGHT + 7199) == 3200
        assert _bri("Evening", NIGHT + 7199) == 180
        assert _kel("Evening", NIGHT + _H, evening_kelvin=4000, night_kelvin=2200) == 4000

    def test_every_phase_forced_during_real_evening(self):
        now_ts = EVENING + _H
        for phase in ("Morning", "Day", "Night"):
            assert (_bri(phase, now_ts), _kel(phase, now_ts)) == DEFAULTS[phase]


class TestKelvinToRgb:
    def test_reference_points(self):
        assert kelvin_to_rgb(6600) == (255, 255, 255)  # where all channels cross 255
        assert kelvin_to_rgb(1000) == (255, 68, 0)
        assert kelvin_to_rgb(10000) == (202, 218, 255)

    def test_warmer_as_kelvin_drops(self):
        high, mid, low = kelvin_to_rgb(6500), kelvin_to_rgb(4000), kelvin_to_rgb(2000)
        assert low[0] >= mid[0] >= high[0]
        assert low[2] <= mid[2] <= high[2]

    def test_below_1000k_clamps(self):
        """HA's conversion clamps at 1000K; compute_curve's schema can reach it."""
        assert kelvin_to_rgb(500) == kelvin_to_rgb(1000)
        assert kelvin_to_rgb(999) == kelvin_to_rgb(1000)

    @pytest.mark.parametrize("phase,start", PHASE_STARTS)
    def test_targets_rgb_is_the_kelvin_converted(self, phase, start):
        targets = _targets(phase, start)
        assert targets["rgb_color"] == kelvin_to_rgb(targets["kelvin"])


# --- phase_marks --------------------------------------------------------


def _observed_transitions(boundaries, step=60):
    """The day's phase changes, read off phase_at(). A leading Night run is
    dropped: it's the wrap-around of the Night the day returns to."""
    runs = []
    previous = None
    for i in range(0, 86400, step):
        current = phase_at(i, *boundaries)
        if current != previous:
            runs.append((current, float(i)))
        previous = current
    if runs and runs[0][0] == "Night":
        runs = runs[1:]
    return runs


# Hour-aligned, so a 60s grid lands on every boundary.
BOUNDARY_CASES = [
    (6 * _H, 8 * _H, 19 * _H, 22 * _H),  # normal
    (10 * _H, 8 * _H, 19 * _H, 22 * _H),  # Morning after Day -> no Morning
    (6 * _H, 8 * _H, 7 * _H, 22 * _H),  # Evening before Day -> no Day
    (6 * _H, 8 * _H, 19 * _H, 18 * _H),  # Night before Evening -> no Evening
    (6 * _H, 6 * _H, 19 * _H, 22 * _H),  # Morning == Day -> no Morning
    (6 * _H, 8 * _H, 8 * _H, 22 * _H),  # Day == Evening -> no Day
    (22 * _H, 20 * _H, 18 * _H, 16 * _H),  # fully reversed -> only Night
    (0, 8 * _H, 19 * _H, 22 * _H),  # Morning at midnight -> no leading Night
    (6 * _H, 6 * _H, 6 * _H, 6 * _H),  # everything on one instant
]


class TestPhaseMarks:
    @pytest.mark.parametrize("boundaries", BOUNDARY_CASES)
    def test_matches_what_phase_at_actually_does(self, boundaries):
        assert phase_marks(*boundaries) == _observed_transitions(boundaries)

    @pytest.mark.parametrize("boundaries", BOUNDARY_CASES)
    def test_never_marks_a_phase_that_never_occurs(self, boundaries):
        occurring = {phase_at(i, *boundaries) for i in range(0, 86400, 60)}
        for name, _ in phase_marks(*boundaries):
            assert name in occurring, f"{name} is marked but never happens"

    @pytest.mark.parametrize("boundaries", BOUNDARY_CASES)
    def test_ordered_and_ending_on_night(self, boundaries):
        marks = phase_marks(*boundaries)
        starts = [t for _, t in marks]
        assert starts == sorted(starts)
        assert len(starts) == len(set(starts))
        assert marks == [] or marks[-1][0] == "Night"

    def test_a_normal_schedule_marks_all_four_in_order(self):
        assert phase_marks(6 * _H, 8 * _H, 19 * _H, 22 * _H) == [
            ("Morning", 6.0 * _H),
            ("Day", 8.0 * _H),
            ("Evening", 19.0 * _H),
            ("Night", 22.0 * _H),
        ]

    def test_the_phase_after_an_unreachable_one_starts_at_the_later_boundary(self):
        marks = dict(phase_marks(10 * _H, 8 * _H, 19 * _H, 22 * _H))
        assert "Morning" not in marks
        assert marks["Day"] == 10.0 * _H

    def test_a_day_that_never_leaves_night_has_no_marks(self):
        assert phase_marks(22 * _H, 20 * _H, 18 * _H, 16 * _H) == []
        assert phase_marks(6 * _H, 6 * _H, 6 * _H, 6 * _H) == []

    def test_a_phase_starting_at_midnight_is_marked(self):
        assert phase_marks(0, 8 * _H, 19 * _H, 22 * _H) == [
            ("Morning", 0),
            ("Day", 8.0 * _H),
            ("Evening", 19.0 * _H),
            ("Night", 22.0 * _H),
        ]
