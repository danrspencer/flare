"""Writing the blueprint in a language from a table."""

import pytest

from custom_components.flare.blueprint_translation import language_for, translate
from custom_components.flare.blueprint_version import language_from_description, version_from_description

BLUEPRINT = {
    "blueprint": {
        "name": "FLARE",
        "description": "Lighting.\n\nBlueprint version 1.2.3 - the integration raises a repair.\n",
        "domain": "automation",
        "input": {
            "wait": {
                "name": "Wait time",
                "description": "How long.",
                "default": 120,
                "selector": {"number": {"min": 0, "unit_of_measurement": "seconds"}},
            },
            "settings": {
                "name": "Settings",
                "collapsed": True,
                "input": {
                    "rgb_phases": {
                        "name": "Prefer RGB During",
                        "default": ["Evening"],
                        "selector": {"select": {"options": ["Morning", "Evening"], "multiple": True}},
                    },
                    "untouched": {"name": "Left in English", "selector": {"boolean": {}}},
                },
            },
        },
    },
    "triggers": [],
}

TABLE = {
    "blueprint": {"description": "Licht.", "stamp": "die Integration meldet eine Reparatur."},
    "wait": {"name": "Wartezeit", "description": "Wie lange.", "unit": "Sekunden"},
    "settings": {"name": "Einstellungen"},
    "rgb_phases": {"name": "RGB bevorzugen", "options": {"Morning": "Morgen", "Evening": "Abend"}},
}


def test_text_is_translated_and_everything_else_kept():
    data = translate(BLUEPRINT, TABLE, "de")
    wait = data["blueprint"]["input"]["wait"]
    settings = data["blueprint"]["input"]["settings"]

    assert (wait["name"], wait["description"]) == ("Wartezeit", "Wie lange.")
    assert wait["default"] == 120
    assert wait["selector"] == {"number": {"min": 0, "unit_of_measurement": "Sekunden"}}
    assert settings["name"] == "Einstellungen"
    assert settings["collapsed"] is True
    assert data["blueprint"]["name"] == "FLARE"
    assert data["triggers"] == []


def test_options_keep_their_english_values_under_a_label():
    """The phase names are the schedule sensor's states, so stored inputs
    must still hold them."""
    rgb = translate(BLUEPRINT, TABLE, "de")["blueprint"]["input"]["settings"]["input"]["rgb_phases"]

    assert rgb["selector"]["select"]["options"] == [
        {"value": "Morning", "label": "Morgen"},
        {"value": "Evening", "label": "Abend"},
    ]
    assert rgb["default"] == ["Evening"]


def test_an_entry_the_table_lacks_stays_english():
    untouched = translate(BLUEPRINT, TABLE, "de")["blueprint"]["input"]["settings"]["input"]["untouched"]

    assert untouched["name"] == "Left in English"


def test_the_description_is_translated_and_stamped_with_the_language():
    description = translate(BLUEPRINT, TABLE, "de")["blueprint"]["description"]

    assert description.startswith("Licht.")
    assert "die Integration meldet eine Reparatur." in description
    assert version_from_description(description) == "1.2.3"
    assert language_from_description(description) == "de"


def test_no_table_leaves_english_stamped_as_english():
    data = translate(BLUEPRINT, None, "en")

    assert data["blueprint"]["input"] == BLUEPRINT["blueprint"]["input"]
    assert data["blueprint"]["description"].startswith("Lighting.")
    assert language_from_description(data["blueprint"]["description"]) == "en"
    assert version_from_description(data["blueprint"]["description"]) == "1.2.3"


def test_the_original_is_left_as_it_was():
    translate(BLUEPRINT, TABLE, "de")

    assert BLUEPRINT["blueprint"]["input"]["wait"]["name"] == "Wait time"
    assert "(de)" not in BLUEPRINT["blueprint"]["description"]


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("de", "de"), ("de-CH", "de"), ("pt-BR", "pt-BR"), ("pt-PT", "en"), ("fr", "en"), (None, "en")],
)
def test_the_table_follows_home_assistants_language(configured, expected):
    assert language_for(configured, ["de", "pt-BR"]) == expected
