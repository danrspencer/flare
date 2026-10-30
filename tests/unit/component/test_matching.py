"""matching.shows(): whether a light's reported values show a target, for
override protection and grouping alike. Sections follow matching.py's
docstring."""

import pytest

from custom_components.flare.tracking.matching import Tolerance, reported_kelvin, shown, shows

KELVIN = {"brightness": 200, "color_temp_kelvin": 3000}
RGB = {"brightness": 200, "rgb_color": [255, 120, 10]}


def _ct(brightness=200, kelvin=3000, **attributes):
    return {"brightness": brightness, "color_mode": "color_temp", "color_temp_kelvin": kelvin, **attributes}


def _xy(x, y, brightness=255, **attributes):
    """A colour mode, as HA reports it: no color_temp_kelvin."""
    return {"brightness": brightness, "color_mode": "xy", "color_temp_kelvin": None, "xy_color": [x, y], **attributes}


class TestTargets:
    @pytest.mark.parametrize("target", [None, {}, {"state": "off"}, {"color_temp_kelvin": 3000}, {"brightness": 200}])
    def test_a_target_without_a_brightness_and_a_colour_never_matches(self, target):
        assert not shows(_ct(), target)


class TestBrightness:
    def test_within_the_rounding_floor(self):
        """2 points, whatever the percentage."""
        assert shows(_ct(198), KELVIN) and shows(_ct(202), KELVIN)
        assert not shows(_ct(197), KELVIN)

    def test_a_light_reporting_none_does_not_match(self):
        assert not shows(_ct(None), KELVIN)

    def test_the_minimum_change_widens_it(self):
        """5% of 200 is 10."""
        assert shows(_ct(190), KELVIN, Tolerance(min_brightness_change=5))
        assert not shows(_ct(189), KELVIN, Tolerance(min_brightness_change=5))


class TestReadingKelvin:
    def test_color_temp_mode_reports_it_directly(self):
        assert reported_kelvin({"color_temp_kelvin": 3000, "xy_color": [0.5, 0.4]}) == 3000

    @pytest.mark.parametrize(
        ("xy", "kelvin"),
        [((0.3124, 0.3226), 6575), ((0.4599, 0.4106), 2698), ((0.5019, 0.4152), 2233)],
        ids=["6500K, seen live", "2700K", "2200K"],
    )
    def test_a_white_in_xy_is_read_as_kelvin(self, xy, kelvin):
        assert reported_kelvin(_xy(*xy)) == kelvin

    @pytest.mark.parametrize("xy", [(0.17, 0.7), (0.7, 0.3), (0.38, 0.28)], ids=["green", "red", "pink"])
    def test_a_colour_has_no_kelvin(self, xy):
        assert reported_kelvin(_xy(*xy)) is None

    def test_nothing_to_read(self):
        assert reported_kelvin({}) is None
        assert reported_kelvin({"xy_color": "nonsense"}) is None


class TestKelvin:
    def test_without_a_tolerance_only_the_same_mired_matches(self):
        """3000K and 3002K floor to mired 333; 3010K to 332."""
        assert shows(_ct(kelvin=3002), KELVIN)
        assert not shows(_ct(kelvin=3010), KELVIN)

    def test_the_same_mired_matches_beyond_tolerance(self):
        """4373K floors to mired 228, which reads back as 4385K."""
        assert shows(_ct(255, 4385), {"brightness": 255, "color_temp_kelvin": 4373})

    def test_the_minimum_change_covers_a_bulb_reporting_a_mired_off(self):
        """Seen live: asked for 4294K (232.9 mireds), reported 4312K (231.9)."""
        target = {"brightness": 255, "color_temp_kelvin": 4294}
        assert not shows(_ct(255, 4312), target)
        assert shows(_ct(255, 4312), target, Tolerance(min_color_temp_change=5))

    def test_the_minimum_change_widens_it_in_mireds(self):
        """3000K is 333.3 mireds, 3040K is 328.9."""
        assert shows(_ct(kelvin=3040), KELVIN, Tolerance(min_color_temp_change=5))
        assert not shows(_ct(kelvin=3100), KELVIN, Tolerance(min_color_temp_change=5))

    def test_a_white_reported_in_xy_is_compared_as_kelvin_not_rgb(self):
        """Seen live: spots asked for 6578K reported xy (0.3124, 0.3226), and
        rgb_color (242, 248, 255) - HA's xy conversion, not its Kelvin one."""
        target = {"brightness": 255, "color_temp_kelvin": 6578}
        assert shows(_xy(0.3124, 0.3226, rgb_color=[242, 248, 255]), target)
        assert not shows(_xy(0.3124, 0.3226), {"brightness": 255, "color_temp_kelvin": 3000})

    def test_a_colour_is_not_mistaken_for_the_white_its_xy_converts_to(self):
        """Green's xy converts to ~8049K."""
        assert not shows(_xy(0.17, 0.7), {"brightness": 255, "color_temp_kelvin": 8049})


class TestAdvertisedRange:
    TARGET = {"brightness": 255, "color_temp_kelvin": 6578}

    @pytest.mark.parametrize(
        ("attributes", "expected"),
        [
            (_ct(255, 4000, max_color_temp_kelvin=4000), True),
            (_xy(0.3805, 0.3768, max_color_temp_kelvin=4000), True),
            (_ct(255, 6578, max_color_temp_kelvin=4000), True),
            (_ct(255, 2700, max_color_temp_kelvin=4000), False),
            (_ct(255, 4000), False),
        ],
        ids=[
            "parked at its ceiling",
            "parked at its ceiling, in xy",
            "beyond what it advertises",
            "elsewhere",
            "no advertised range",
        ],
    )
    def test_the_target_as_asked_or_clamped_to_the_range(self, attributes, expected):
        assert shows(attributes, self.TARGET) is expected

    def test_the_floor_too(self):
        assert shows(_ct(255, 2202, min_color_temp_kelvin=2202), {"brightness": 255, "color_temp_kelvin": 2000})


class TestRgb:
    def test_within_the_rounding_floor(self):
        """4 in total, however the colour tolerance is set."""
        assert shows({"brightness": 200, "rgb_color": [255, 121, 8]}, RGB)
        assert not shows({"brightness": 200, "rgb_color": [255, 122, 7]}, RGB)

    def test_the_difference_is_summed_across_channels(self):
        """9 in one channel and 12 in all passes nothing that 11 in one fails."""
        target = {"brightness": 200, "rgb_color": [255, 120, 21]}
        tolerance = Tolerance(min_color_temp_change=5)
        assert not shows({"brightness": 200, "rgb_color": [255, 120, 10]}, target, tolerance)
        assert not shows({"brightness": 200, "rgb_color": [254, 129, 19]}, target, tolerance)
        assert shows({"brightness": 200, "rgb_color": [254, 126, 18]}, target, tolerance)

    def test_it_follows_the_colour_tolerance(self):
        """Twice the mireds: 10 at the default 5."""
        reported = {"brightness": 200, "rgb_color": [255, 126, 14]}
        assert shows(reported, RGB, Tolerance(min_color_temp_change=5))
        assert not shows(reported, RGB, Tolerance(min_color_temp_change=4))

    def test_a_malformed_rgb_does_not_match(self):
        assert not shows({"brightness": 200, "rgb_color": [255, 120, 10, 0]}, RGB)
        assert not shows({"brightness": 200}, RGB)

    def test_only_an_rgb_target_reads_rgb(self):
        """A Kelvin target never falls back to comparing rgb_color."""
        assert not shows({"brightness": 255, "rgb_color": [255, 255, 252]}, {"brightness": 255, "color_temp_kelvin": 6578})


class TestShown:
    """What a light shows, as a target - what adoption claims."""

    def test_a_white_is_its_kelvin_even_in_xy(self):
        assert shown(_ct(200, 3000)) == {"brightness": 200, "color_temp_kelvin": 3000}
        assert shown(_xy(0.3124, 0.3226, rgb_color=[242, 248, 255])) == {"brightness": 255, "color_temp_kelvin": 6575}

    def test_a_colour_is_its_rgb(self):
        assert shown(_xy(0.17, 0.7, rgb_color=[0, 255, 0])) == {"brightness": 255, "rgb_color": [0, 255, 0]}

    def test_it_shows_itself(self):
        for attributes in (_ct(200, 3000), _xy(0.3124, 0.3226), _xy(0.17, 0.7, rgb_color=[0, 255, 0])):
            assert shows(attributes, shown(attributes))
