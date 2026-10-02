"""The schedule document: what export writes and what import accepts."""

import pytest

from custom_components.flare.schedule.coordinator import CURVE_KEYS, TIME_KEYS
from custom_components.flare.schedule.curve import DEFAULT_CURVE_VALUES
from custom_components.flare.schedule.transfer import ScheduleError, dump, parse

EVERYTHING = {
    **DEFAULT_CURVE_VALUES,
    "morning_time": "06:00:00",
    "day_time": "08:30:00",
    "evening_earliest_time": "17:00:00",
    "evening_latest_time": "20:00:00",
    "night_time": "22:15:30",
}


def test_every_value_survives_a_round_trip():
    assert parse(dump(EVERYTHING)) == EVERYTHING


def test_the_document_is_keyed_by_phase_with_evening_limits_in_place_of_a_start():
    text = dump(EVERYTHING)

    assert text.startswith('morning:\n  time: "06:00"\n  brightness: 255\n')
    assert '\nevening:\n  earliest: "17:00"\n  latest: "20:00"\n' in text
    assert '\nnight:\n  time: "22:15:30"\n' in text


def test_a_value_with_no_entity_is_left_out():
    assert dump({"night_kelvin": 2000}) == "night:\n  kelvin: 2000\n"


def test_a_partial_document_names_only_what_it_sets():
    assert parse("day:\n  brightness: 200\n") == {"day_brightness": 200}


def test_json_is_accepted():
    assert parse('{"morning": {"time": "6:05", "kelvin": 6000}}') == {
        "morning_time": "06:05:00",
        "morning_kelvin": 6000,
    }


@pytest.mark.parametrize(
    "text, mentions",
    [
        ("", "Expected phases"),
        ("- morning", "Expected phases"),
        ("dusk:\n  time: '19:00'", "Unknown phase 'dusk'"),
        ("morning: 6", "'morning' should hold settings"),
        ("evening:\n  time: '18:00'", "Unknown setting 'evening.time'"),
        ("morning:\n  colour: 3000", "Unknown setting 'morning.colour'"),
        ("night:\n  time: '24:00'", "'night.time' should be a time"),
        ("night:\n  time: 'late'", "'night.time' should be a time"),
        ("day:\n  brightness: 256", "from 0 to 255"),
        ("day:\n  kelvin: 999", "from 1000 to 10000"),
        ("day:\n  brightness_transition: 1441", "from 0 to 1440"),
        ("day:\n  brightness: 12.5", "whole number"),
        ("day: [", "Not valid YAML"),
    ],
)
def test_a_mistake_is_explained_in_the_documents_own_terms(text, mentions):
    with pytest.raises(ScheduleError, match=mentions):
        parse(text)


def test_every_entity_has_a_place_in_the_document():
    assert set(parse(dump(EVERYTHING))) == set(TIME_KEYS) | set(CURVE_KEYS)
