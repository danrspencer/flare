from datetime import UTC, datetime, timedelta

from custom_components.flare.tracking.ticker import next_tick, slot_offsets


def _at(hour, minute, second=0):
    return datetime(2026, 9, 27, hour, minute, second, tzinfo=UTC)


class TestSlotOffsets:
    def test_zones_are_a_gap_apart_starting_on_the_boundary(self):
        assert slot_offsets(3, 1, 2) == [timedelta(0), timedelta(seconds=2), timedelta(seconds=4)]

    def test_the_gap_shrinks_so_every_zone_fits_in_the_interval(self):
        # 60 zones one second apart fill the minute; 120 can't.
        assert slot_offsets(120, 1, 1)[-1] == timedelta(seconds=59.5)

    def test_no_zones(self):
        assert slot_offsets(0, 1, 1) == []


class TestNextTick:
    def test_the_next_boundary_plus_offset(self):
        assert next_tick(_at(19, 0, 2), 1, timedelta(seconds=1)) == _at(19, 1, 1)

    def test_a_slot_still_ahead_in_this_interval(self):
        assert next_tick(_at(19, 0, 2), 1, timedelta(seconds=10)) == _at(19, 0, 10)

    def test_exactly_at_the_slot_means_the_next_one(self):
        assert next_tick(_at(19, 1, 1), 1, timedelta(seconds=1)) == _at(19, 2, 1)

    def test_boundaries_fall_on_the_clocks_minutes(self):
        assert next_tick(_at(19, 0, 2), 2, timedelta(seconds=1)) == _at(19, 2, 1)
        assert next_tick(_at(19, 7, 0), 15, timedelta(0)) == _at(19, 15, 0)
