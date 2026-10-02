"""A schedule as a YAML document, for export and import:

    morning:
      time: "06:00"
      brightness: 255
      kelvin: 6667
      brightness_transition: 30
      kelvin_transition: 30
    day: ...
    evening:
      earliest: "17:00"
      latest: "20:00"
      ...
    night: ...

Keyed by phase, each field mapping to one time or number entity. An
import may leave anything out, which keeps its current value. Times may
be out of order, as the entities allow (see curve.phase_marks)."""

from __future__ import annotations

import re

import yaml

from .coordinator import CURVE_KEYS, TIME_KEYS
from .curve import PHASE_ORDER, value_range

PHASES = tuple(p.lower() for p in PHASE_ORDER)

# Evening has two limits around sunset where every other phase has a start.
_TIME_FIELDS = {
    "morning": {"time": "morning_time"},
    "day": {"time": "day_time"},
    "evening": {"earliest": "evening_earliest_time", "latest": "evening_latest_time"},
    "night": {"time": "night_time"},
}
_NUMBER_FIELDS = ("brightness", "kelvin", "brightness_transition", "kelvin_transition")

# (phase, field) -> entity key, in document order.
FIELDS: dict[tuple[str, str], str] = {}
for _phase in PHASES:
    for _field, _key in _TIME_FIELDS[_phase].items():
        FIELDS[(_phase, _field)] = _key
    for _field in _NUMBER_FIELDS:
        FIELDS[(_phase, _field)] = f"{_phase}_{_field}"

assert set(FIELDS.values()) == set(TIME_KEYS) | set(CURVE_KEYS)

_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


class ScheduleError(ValueError):
    """A document that can't be imported. The message says why, in terms of
    the document's own keys."""


def to_document(values: dict[str, str | int]) -> dict[str, dict[str, str | int]]:
    """Entity key -> value (times as "HH:MM[:SS]") into the nested document.
    Keys with no value are left out."""
    doc: dict[str, dict[str, str | int]] = {}
    for (phase, field), key in FIELDS.items():
        if key in values:
            value = values[key]
            doc.setdefault(phase, {})[field] = _short_time(value) if key in TIME_KEYS else value
    return doc


def dump(values: dict[str, str | int]) -> str:
    """Written out by hand rather than yaml.safe_dump, which quotes a time
    only when it happens to look like a YAML 1.1 number. Every time is
    quoted here, so any YAML parser reads it back as a string. The docs
    playground writes the same text (docs/assets/js/schedule-yaml.js)."""
    lines = []
    for phase, fields in to_document(values).items():
        lines.append(f"{phase}:")
        for field, value in fields.items():
            lines.append(f'  {field}: "{value}"' if isinstance(value, str) else f"  {field}: {value}")
    return "\n".join(lines) + "\n"


def parse(text: str) -> dict[str, str | int]:
    """The document into entity key -> value, times as "HH:MM:SS". Raises
    ScheduleError on anything it can't import, before anything is applied.

    BaseLoader reads every scalar as a string: YAML 1.1 would otherwise
    read an unquoted 06:30 as the base-60 number 390."""
    try:
        doc = yaml.load(text, Loader=yaml.BaseLoader)  # noqa: S506 - BaseLoader builds only str/list/dict
    except yaml.YAMLError as err:
        raise ScheduleError(f"Not valid YAML: {err}") from err
    if not isinstance(doc, dict) or not doc:
        raise ScheduleError("Expected phases (morning, day, evening, night), each with its settings.")

    values: dict[str, str | int] = {}
    for phase, fields in doc.items():
        if phase not in PHASES:
            raise ScheduleError(f"Unknown phase '{phase}'. Expected one of: {', '.join(PHASES)}.")
        if not isinstance(fields, dict):
            raise ScheduleError(f"'{phase}' should hold settings like brightness and kelvin.")
        for field, raw in fields.items():
            key = FIELDS.get((phase, field))
            if key is None:
                known = ", ".join(f for p, f in FIELDS if p == phase)
                raise ScheduleError(f"Unknown setting '{phase}.{field}'. Expected one of: {known}.")
            values[key] = _parse_time(phase, field, raw) if key in TIME_KEYS else _parse_number(phase, field, key, raw)
    return values


def _parse_time(phase: str, field: str, raw) -> str:
    match = _TIME.match(raw) if isinstance(raw, str) else None
    if match:
        hour, minute, second = int(match[1]), int(match[2]), int(match[3] or 0)
        if hour < 24 and minute < 60 and second < 60:
            return f"{hour:02d}:{minute:02d}:{second:02d}"
    raise ScheduleError(f"'{phase}.{field}' should be a time like \"06:30\", not {raw!r}.")


def _parse_number(phase: str, field: str, key: str, raw) -> int:
    low, high = value_range(key)
    try:
        number = int(raw) if isinstance(raw, str) else None
    except ValueError:
        number = None
    if number is None or not low <= number <= high:
        raise ScheduleError(f"'{phase}.{field}' should be a whole number from {low} to {high}, not {raw!r}.")
    return number


def _short_time(value) -> str:
    """A time entity's "HH:MM:SS" as "HH:MM" when the seconds are zero."""
    text = str(value)
    return text[:5] if len(text) == 8 and text.endswith(":00") else text
