"""Each blueprint translation says everything the English blueprint does
and no more, and was made from the English as it reads now."""

import re

import pytest
import yaml

from custom_components.flare.blueprint_translation import TRANSLATIONS, english, source_of
from tests.support import load_blueprint

LANGUAGES = sorted(TRANSLATIONS.glob("*.yaml"))
ENGLISH = english(load_blueprint())


def test_there_are_languages_to_check():
    assert LANGUAGES


def _table(path):
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize("path", LANGUAGES, ids=lambda p: p.stem)
def test_every_input_and_section_is_translated_and_no_more(path):
    """An entry for a key the blueprint lost is dead text; a key without one
    shows in English among the translated ones."""
    table = _table(path)

    assert sorted(set(ENGLISH) - set(table)) == [], "untranslated"
    assert sorted(set(table) - set(ENGLISH)) == [], "no longer in the blueprint"


@pytest.mark.parametrize("path", LANGUAGES, ids=lambda p: p.stem)
def test_each_entry_translates_exactly_what_the_english_has(path):
    table = _table(path)

    for key, text in ENGLISH.items():
        entry = table.get(key, {})
        assert sorted(set(entry) - {"source"}) == sorted(text), key
        if "options" in text:
            assert sorted(entry["options"]) == sorted(text["options"]), key


@pytest.mark.parametrize("path", LANGUAGES, ids=lambda p: p.stem)
def test_each_entry_was_translated_from_the_english_as_it_reads_now(path):
    """Rewording the English changes its hash: revisit the translation, then
    record the new one."""
    table = _table(path)

    stale = {
        key: f"source: {source_of(text)} for {text}"
        for key, text in ENGLISH.items()
        if table.get(key, {}).get("source") != source_of(text)
    }
    assert stale == {}


_LINK = re.compile(r"\]\((https?://[^)]+)\)")


@pytest.mark.parametrize("path", LANGUAGES, ids=lambda p: p.stem)
def test_a_translation_keeps_the_english_links(path):
    table = _table(path)

    for key, text in ENGLISH.items():
        if "description" in text:
            assert _LINK.findall(table[key]["description"]) == _LINK.findall(text["description"]), key
