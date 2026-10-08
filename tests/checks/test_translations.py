"""strings.json is the source; Home Assistant shows a custom integration
translations/en.json, so the two must say the same."""

import json

from tests.support import COMPONENT


def test_the_english_translations_are_the_strings():
    strings = json.loads((COMPONENT / "strings.json").read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())

    assert english == strings, "copy strings.json to translations/en.json"
