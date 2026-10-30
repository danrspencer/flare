"""The blueprint in the house's language. Home Assistant has no
translations for a blueprint, so FLARE writes its text in Home
Assistant's language as it installs or updates it. Pure, so it's testable
on plain dicts; blueprint_check.py reads the files.

A table (blueprints/translations/<language>.yaml) gives each input's and
section's text by its key, and the blueprint's own under `blueprint`. Only text
changes: keys, defaults and selectors stay, so a room's stored inputs
still match, and select options keep their English values (phase names
are the schedule sensor's states) under a translated label.

Each entry records a `source`, a hash of the English it was translated
from, so rewording the English shows which translations need revisiting.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from homeassistant.components.blueprint.const import CONF_BLUEPRINT, CONF_INPUT
from homeassistant.const import CONF_DESCRIPTION, CONF_NAME, CONF_OPTIONS, CONF_SELECTOR, CONF_UNIT_OF_MEASUREMENT

from .blueprint_version import version_from_description, with_language

TRANSLATIONS = Path(__file__).parent / "blueprints" / "translations"

ENGLISH = "en"

# The stamp sentence: "Blueprint version 2.0.0 - <the rest>".
_STAMP = re.compile(r"Blueprint version\s+\S+\s+-\s+(.*)", re.DOTALL)


def language_for(configured: str | None, available: Iterable[str]) -> str:
    """The table for Home Assistant's language: exact ("pt-BR"), else its
    base ("de" for "de-CH"), else English."""
    available = set(available)
    if not configured:
        return ENGLISH
    for candidate in (configured, configured.split("-")[0]):
        if candidate in available:
            return candidate
    return ENGLISH


def _split(description: str) -> tuple[str, str]:
    """A blueprint description as its prose and the stamp sentence's text."""
    match = _STAMP.search(description)
    if not match:
        raise ValueError("the blueprint's description has no version stamp")
    return description[: match.start()].strip(), " ".join(match.group(1).split())


def _text(value: Mapping[str, Any]) -> dict[str, Any]:
    """An input's or section's translatable English, its whitespace
    collapsed so re-wrapping the YAML doesn't change it."""
    text: dict[str, Any] = {k: " ".join(value[k].split()) for k in (CONF_NAME, CONF_DESCRIPTION) if k in value}
    for config in (value.get(CONF_SELECTOR) or {}).values():
        if not isinstance(config, Mapping):
            continue
        if CONF_OPTIONS in config:
            text["options"] = list(config[CONF_OPTIONS])
        if CONF_UNIT_OF_MEASUREMENT in config:
            text["unit"] = config[CONF_UNIT_OF_MEASUREMENT]
    return text


def _each_input(inputs: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    """Every input and section, sections' own inputs included."""
    for key, value in inputs.items():
        if value is None:
            continue
        yield key, value
        if CONF_INPUT in value:
            yield from _each_input(value[CONF_INPUT])


def english(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Everything a table translates, by the key it's given under: the
    blueprint's own text as "blueprint", then each input and section."""
    prose, stamp = _split(data[CONF_BLUEPRINT][CONF_DESCRIPTION])
    text = {"blueprint": {"description": prose, "stamp": stamp}}
    text.update((key, _text(value)) for key, value in _each_input(data[CONF_BLUEPRINT][CONF_INPUT]))
    return text


def source_of(text: Mapping[str, Any]) -> str:
    """The hash a translation of `text` records as its `source`."""
    return hashlib.sha256(json.dumps(text, sort_keys=True).encode()).hexdigest()[:8]


def translate(data: Mapping[str, Any], table: Mapping[str, Any] | None, language: str) -> dict[str, Any]:
    """The blueprint `data` written in `language` from `table`, stamped
    with the language. No table is English, stamped "en"."""
    blueprint = dict(data[CONF_BLUEPRINT])
    description = blueprint[CONF_DESCRIPTION]
    if table:
        own = table["blueprint"]
        version = version_from_description(description)
        description = f"{own['description'].strip()}\n\nBlueprint version {version} - {own['stamp'].strip()}\n"
        blueprint[CONF_INPUT] = _inputs(blueprint[CONF_INPUT], table)
    blueprint[CONF_DESCRIPTION] = with_language(description, language)
    return {**data, CONF_BLUEPRINT: blueprint}


def _inputs(inputs: Mapping[str, Any], table: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _input(value, table.get(key, {}), table) for key, value in inputs.items()}


def _input(value: Mapping[str, Any] | None, entry: Mapping[str, Any], table: Mapping[str, Any]) -> Any:
    if value is None:
        return None
    value = dict(value)
    for field in (CONF_NAME, CONF_DESCRIPTION):
        if field in entry:
            value[field] = entry[field]
    if CONF_INPUT in value:
        value[CONF_INPUT] = _inputs(value[CONF_INPUT], table)
    if CONF_SELECTOR in value:
        value[CONF_SELECTOR] = {kind: _selector(config, entry) for kind, config in value[CONF_SELECTOR].items()}
    return value


def _selector(config: Any, entry: Mapping[str, Any]) -> Any:
    if not isinstance(config, Mapping):
        return config
    config = dict(config)
    if "options" in entry and CONF_OPTIONS in config:
        labels = entry["options"]
        config[CONF_OPTIONS] = [{"value": option, "label": labels.get(option, option)} for option in config[CONF_OPTIONS]]
    if "unit" in entry and CONF_UNIT_OF_MEASUREMENT in config:
        config[CONF_UNIT_OF_MEASUREMENT] = entry["unit"]
    return config
