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
BLUEPRINT_VERSION = "1.0.0-beta.18"

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


def is_outdated(installed: str | None) -> bool:
    """Inequality rather than "older than", so a blueprint from an
    abandoned beta is also moved back onto this release."""
    return installed != BLUEPRINT_VERSION
