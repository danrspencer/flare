"""
Which version of the blueprint is installed, and whether it is the one
this integration shipped with.

The two halves of FLARE deploy separately - HACS updates the
integration, and the blueprint has to be re-imported by hand - so a
house can quite easily end up running a blueprint from three releases
ago against today's services. Nothing announces that. It just behaves
oddly.

BLUEPRINT_VERSION IS NOT THE INTEGRATION'S VERSION. It is the version in
which the blueprint itself last changed, so a release that only touches
Python doesn't tell every user to go and re-import an identical file.
That is the whole reason it is a separate constant rather than being
read from the manifest, and it means it has to be bumped by hand when
the blueprint changes - `tests/test_blueprint_version.py` is what makes
that mistake loud, since a stale stamp otherwise fails silently and
users simply never hear about the update.

The version travels in the blueprint's own `description`, which is not
where you would put it given a free choice. Home Assistant's blueprint
schema (homeassistant/components/blueprint/schemas.py) validates the
`blueprint:` block against a CLOSED voluptuous schema - name,
description, domain, source_url, author, homeassistant, input, and
nothing else - so there is no custom key available, and a top-level key
alongside `blueprint:` would end up in the generated automation config
instead. `description` is free text we control, it survives however the
blueprint was imported, it needs no filesystem access to read back
(Blueprint.metadata exposes it), and it has the side benefit of showing
the version to the user in the automation editor, which nothing else
currently does.

Pure - no Home Assistant imports - so the parsing is testable on plain
strings. blueprint_check.py is the half that talks to HA.
"""

from __future__ import annotations

import re

# Bump this WHENEVER blueprints/automation/danspencer/flare.yaml changes,
# and set the same version in that file's description. The test suite
# checks the two agree; nothing checks that you remembered to move them,
# except the CI step that fails a pull request touching the blueprint
# without touching the stamp.
BLUEPRINT_VERSION = "0.16.0-beta.5"

# Matches the line the blueprint's description carries. Deliberately
# loose about what follows the number so the sentence around it can be
# reworded without breaking every installed copy's version detection.
_VERSION_IN_DESCRIPTION = re.compile(
    r"Blueprint version\s+(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)"
)


def version_from_description(description: str | None) -> str | None:
    """The blueprint version named in a description, or None.

    None means "an older blueprint than the one that started stamping
    itself" as well as "not one of ours", and both want the same
    outcome: offer the update. Callers decide which blueprints to ask
    about; this only reads the string.
    """
    if not description:
        return None
    match = _VERSION_IN_DESCRIPTION.search(description)
    return match.group(1) if match else None


def is_outdated(installed: str | None) -> bool:
    """Does this installed version want updating?

    A plain inequality, not a "newer than" comparison. Someone running a
    blueprint from a beta that was later abandoned should be told to get
    back onto the released one, and an unstamped blueprint (None) is
    every copy released before this check existed.
    """
    return installed != BLUEPRINT_VERSION
