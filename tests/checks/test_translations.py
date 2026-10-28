"""strings.json is the source; Home Assistant shows a custom integration
translations/en.json, so the two must say the same, and every other
language the same things."""

import json
import string

import pytest

from tests.support import COMPONENT


def test_the_english_translations_are_the_strings():
    strings = json.loads((COMPONENT / "strings.json").read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())

    assert english == strings, "copy strings.json to translations/en.json"


def _strings(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str):
        yield path, node


def test_placeholders_are_plain_names():
    """hassfest parses each string with Python's formatter, so ICU plurals
    and other nested braces fail validation."""
    strings = json.loads((COMPONENT / "strings.json").read_text())

    for path, text in _strings(strings):
        for _literal, field, spec, _conversion in string.Formatter().parse(text):
            assert field is None or (field.isidentifier() and not spec), f"{path}: {text}"


def _fields(text: str) -> set[str]:
    return {field for _literal, field, _spec, _conversion in string.Formatter().parse(text) if field}


OTHER_LANGUAGES = sorted(p for p in (COMPONENT / "translations").glob("*.json") if p.name != "en.json")


def test_there_are_other_languages_to_check():
    assert OTHER_LANGUAGES


@pytest.mark.parametrize("path", OTHER_LANGUAGES, ids=lambda p: p.stem)
def test_every_language_says_everything_english_does_and_no_more(path):
    """Keys HA no longer asks for are dead text; keys a language lacks show in
    English."""
    english = dict(_strings(json.loads((COMPONENT / "strings.json").read_text())))
    other = dict(_strings(json.loads(path.read_text())))

    assert sorted(set(english) - set(other)) == [], "untranslated"
    assert sorted(set(other) - set(english)) == [], "no longer in strings.json"


@pytest.mark.parametrize("path", OTHER_LANGUAGES, ids=lambda p: p.stem)
def test_every_language_fills_in_the_same_placeholders(path):
    english = dict(_strings(json.loads((COMPONENT / "strings.json").read_text())))
    other = dict(_strings(json.loads(path.read_text())))

    for key, text in other.items():
        assert _fields(text) == _fields(english[key]), f"{path.name} {key}: {text}"
