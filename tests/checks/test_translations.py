"""strings.json is the source; Home Assistant shows a custom integration
translations/en.json, so the two must say the same."""

import json
import string

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
