"""The dashboard's own text, in the user's Home Assistant language."""

import re

import pytest

from tests.support import WWW
from tests.support.node import js_path, requires_node, run_js
from tests.support.registry import settings_entities

pytestmark = requires_node


@pytest.fixture(scope="module")
def result():
    return run_js(
        f"""
const defined = {{}};
globalThis.customElements.define = (name, cls) => {{ defined[name] = cls; }};
const {{ LANGUAGES, language, localize }} = await import({js_path(WWW / "flare-i18n.js")});
await import({js_path(WWW / "flare-view-strategy.js")});
const {{ sectionConfig }} = await import({js_path(WWW / "flare-section.js")});
const as = (tag) => ({{ ...input, locale: {{ language: tag }} }});
return {{
  tables: LANGUAGES,
  languages: ['de', 'de-CH', 'DE', 'fr', null].map((tag) => language(tag ? {{ locale: {{ language: tag }} }} : {{}})),
  oldHass: language({{ language: 'de' }}),
  filled: localize(as('de'), 'overrides.count_controlled', {{ count: 3 }}),
  unfilled: localize(as('en'), 'overrides.count_controlled'),
  unknownKey: localize(as('de'), 'no.such.key'),
  germanDashboard: await defined['ll-strategy-dashboard-flare'].generate({{}}, as('de')),
  germanOverrides: await defined['ll-strategy-view-flare-lights'].generate({{}}, as('de')),
  germanSection: sectionConfig({{ title: 'Haus', entities: {{}} }}, as('de')),
}};
""",
        {
            "entities": settings_entities(),
            "states": {},
            "areas": {},
            "floors": {},
            "devices": {},
            "config": {"components": ["logbook"]},
        },
    )


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_the_users_language_or_its_base_or_english(result):
    assert result["languages"] == ["de", "de", "de", "en", "en"]


def test_an_older_frontends_language_is_read_too(result):
    """hass.locale arrived after hass.language."""
    assert result["oldHass"] == "de"


def test_placeholders_are_filled_in_and_left_alone_without_a_value(result):
    assert result["filled"] == "3 gesteuert"
    assert result["unfilled"] == "{count} controlled"


def test_a_key_no_language_has_shows_as_itself(result):
    assert result["unknownKey"] == "no.such.key"


@pytest.mark.parametrize("language", ["de"])
def test_every_language_says_everything_english_does_and_no_more(result, language):
    english, other = result["tables"]["en"], result["tables"][language]

    assert sorted(set(english) - set(other)) == [], "untranslated"
    assert sorted(set(other) - set(english)) == [], "not in English"


@pytest.mark.parametrize("language", ["de"])
def test_every_language_fills_in_the_same_placeholders(result, language):
    english, other = result["tables"]["en"], result["tables"][language]

    for key, text in other.items():
        assert _placeholders(text) == _placeholders(english[key]), f"{language} {key}: {text}"


def test_the_views_are_built_in_the_users_language(result):
    view = result["germanOverrides"]
    title, heading, row = view["sections"][0]["cards"]

    assert [v["title"] for v in result["germanDashboard"]["views"]] == ["Überschreibungen"]
    assert (title["heading"], heading["heading"]) == ("Überschreibungen", "Alle Lampen")
    assert [card["name"] for card in row["cards"]] == ["Gesteuert", "Gesteuert", "Überschrieben", "Überschrieben", "Alle zurücksetzen"]
    assert view["sidebar"]["sidebar_label"] == "Aktivität"


def test_a_schedules_names_follow_the_languages_word_order(result):
    """"Morning colour temp" is "Morgen-Farbtemperatur", not word for word."""
    names = [
        card.get("name") or card.get("heading")
        for grid in result["germanSection"]["cards"]
        for card in (grid.get("cards") or [grid])
    ]

    assert "Morgen-Farbtemperatur" in names
    assert "Abend (spätestens)" in names
    assert "Übergänge" in names
