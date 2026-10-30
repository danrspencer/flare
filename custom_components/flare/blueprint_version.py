"""Which blueprint version is installed, and whether it's this release's.
Pure, so parsing is testable on plain strings; blueprint_check.py talks
to HA.

The version lives in the blueprint's `description` because HA validates
the `blueprint:` block against a closed schema, so there's no custom key
to put it in.
"""

from __future__ import annotations

import re

# Written by scripts/release.py, along with the blueprint's stamp.
BLUEPRINT_VERSION = "0.0.0-dev"

# Loose about what follows the number, so the sentence can be reworded.
_VERSION_IN_DESCRIPTION = re.compile(
    r"Blueprint version\s+(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)"
)


def version_from_description(description: str | None) -> str | None:
    """The blueprint version named in a description, or None if it has
    no stamp."""
    if not description:
        return None
    match = _VERSION_IN_DESCRIPTION.search(description)
    return match.group(1) if match else None


# A copy written in a language says which after its version:
# "Blueprint version 2.0.0 (de)". The shipped file has none.
_LANGUAGE_IN_DESCRIPTION = re.compile(_VERSION_IN_DESCRIPTION.pattern + r"\s+\(([A-Za-z-]+)\)")


def language_from_description(description: str | None) -> str | None:
    """The language a copy was written in, or None for one stamped before
    copies carried it."""
    if not description:
        return None
    match = _LANGUAGE_IN_DESCRIPTION.search(description)
    return match.group(2) if match else None


def with_language(description: str, language: str) -> str:
    """`description` with `language` written after its version."""
    return _VERSION_IN_DESCRIPTION.sub(lambda m: f"{m.group(0)} ({language})", description, count=1)


def is_outdated(installed: str | None) -> bool:
    """Inequality rather than "older than", so a blueprint from an
    abandoned beta is also moved back onto this release."""
    return installed != BLUEPRINT_VERSION
