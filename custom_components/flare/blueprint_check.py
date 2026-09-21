"""
Raises a repair when the installed blueprint is older than the one this
release ships with, and updates it in place when the user presses Fix.

FLARE is two halves that deploy separately: HACS updates the
integration, and until now the blueprint had to be re-imported by hand
from a URL nobody remembers. There was nothing telling you the two had
drifted, so the failure mode was a house quietly running a blueprint
from three releases ago against today's services.

Two decisions worth knowing, both deliberate:

**Only blueprints an automation actually uses are reported.** Home
Assistant never removes a blueprint you stop referencing, and this repo
has already produced an orphan on a real instance - importing from
GitHub installs under the repo OWNER's name (`danrspencer/`), which is
not the folder name in this repo (`danspencer/`), so an older copy can
sit at the other path forever. Nagging about a file nothing reads is
noise, and worse, it is noise the user cannot make go away.

**The fix fetches a COMMIT-PINNED tag, not `main`.** A branch URL on
raw.githubusercontent.com can serve a stale copy for minutes after a
push while still reporting success, so a tag URL - which GitHub treats
as immutable and never serves stale - is the only way to be sure the
file that lands is the file we meant. It also means the fix installs
exactly the blueprint this release was tested against, rather than
whatever has landed on main since.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.automation import automations_with_blueprint
from homeassistant.components.automation.helpers import async_get_blueprints
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .blueprint_version import BLUEPRINT_VERSION, is_outdated, version_from_description
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ISSUE_ID = "outdated_blueprint"
MISSING_ISSUE_ID = "blueprint_not_installed"

# Where an install from the repair lands. Home Assistant derives this
# path from the GitHub URL's OWNER, not from the folder name in this
# repo - `danrspencer` with an r, where the repo says `danspencer`
# without. Matching it is deliberate: someone who later uses the
# import badge in the docs overwrites this same file instead of
# ending up with two copies at two paths.
INSTALL_PATH = "danrspencer/flare.yaml"

# Home Assistant renders this as a "Learn more" link on the issue, so
# the description does not have to carry a URL in prose.
QUICKSTART_URL = "https://danrspencer.github.io/flare/installation/"

# Pinned to the tag the stamp names, for the reason in the module
# docstring. The path is this repo's own folder spelling; where it lands
# on the user's disk is decided by Home Assistant from the URL's owner,
# and we overwrite whatever path we actually found rather than assuming.
BLUEPRINT_URL = (
    "https://github.com/danrspencer/flare/blob/v{version}"
    "/blueprints/automation/danspencer/flare.yaml"
)

_OUR_NAME = "FLARE"
_OUR_REPO = "danrspencer/flare"


@dataclass(frozen=True)
class InstalledBlueprint:
    """One copy of our blueprint that some automation is using."""

    path: str  # as Home Assistant knows it, e.g. "danrspencer/flare.yaml"
    version: str | None  # None for anything released before the stamp existed
    automations: int


def _is_ours(blueprint: Blueprint) -> bool:
    """Both tests, because either alone has a hole.

    The name is what a locally-edited copy keeps when its source_url has
    been stripped; the source_url is what an intentionally renamed copy
    keeps. Neither is worth being clever about - a false positive here
    offers someone an update they can decline.
    """
    metadata = blueprint.metadata
    if metadata.get("name") == _OUR_NAME:
        return True
    return _OUR_REPO in (metadata.get("source_url") or "")


async def _ours(hass: HomeAssistant) -> dict[str, Blueprint]:
    """Every copy of our blueprint Home Assistant can load, by path."""
    try:
        installed = await async_get_blueprints(hass).async_get_blueprints()
    except Exception:  # noqa: BLE001 - the check is advisory, never fatal
        _LOGGER.debug("Could not read automation blueprints", exc_info=True)
        return {}
    # async_get_blueprints returns the EXCEPTION for a blueprint that
    # failed to load, not a Blueprint - so this is a type check, not a
    # None check.
    return {
        path: bp
        for path, bp in installed.items()
        if isinstance(bp, Blueprint) and _is_ours(bp)
    }


async def blueprint_is_installed(hass: HomeAssistant) -> bool:
    """Is our blueprint present at all, in use or not?

    Deliberately NOT "is anyone using it". Someone who imported it and
    has not built an automation yet is mid-setup, not stuck, and telling
    them to install what they already have would be wrong.
    """
    return bool(await _ours(hass))


async def outdated_blueprints(hass: HomeAssistant) -> list[InstalledBlueprint]:
    """Every copy of our blueprint that is in use and out of date."""
    installed = await _ours(hass)

    outdated = []
    for path, blueprint in installed.items():
        using = automations_with_blueprint(hass, path)
        if not using:
            continue
        version = version_from_description(blueprint.metadata.get("description"))
        if is_outdated(version):
            outdated.append(InstalledBlueprint(path, version, len(using)))
    return outdated


def describe(blueprints: list[InstalledBlueprint]) -> str:
    """Markdown for the issue and the confirm step."""
    return "\n".join(
        f"- `{b.path}` — version {b.version or 'unknown'}, "
        f"used by {b.automations} automation{'s' if b.automations != 1 else ''}"
        for b in blueprints
    )


async def async_check(hass: HomeAssistant) -> None:
    """Raise whichever of the two blueprint repairs applies.

    They are mutually exclusive by construction: a house with no
    blueprint has nothing that can be out of date, and a house with one
    is not missing it. Both are cleared on the path that doesn't raise
    them, so switching between the two states leaves nothing stale.
    """
    if not await blueprint_is_installed(hass):
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        ir.async_create_issue(
            hass,
            DOMAIN,
            MISSING_ISSUE_ID,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=MISSING_ISSUE_ID,
            learn_more_url=QUICKSTART_URL,
        )
        return

    ir.async_delete_issue(hass, DOMAIN, MISSING_ISSUE_ID)

    outdated = await outdated_blueprints(hass)
    if not outdated:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        translation_placeholders={
            "current": BLUEPRINT_VERSION,
            "blueprints": describe(outdated),
        },
    )


async def _fetch(hass: HomeAssistant):
    """The shipped blueprint, from a commit-pinned tag.

    A tag rather than `main` because raw.githubusercontent.com can serve
    a branch URL stale for minutes after a push while still reporting
    success - so a tag, which GitHub treats as immutable, is the only
    way to be sure the file that lands is the one this release was
    tested against.
    """
    from homeassistant.components.blueprint.importer import fetch_blueprint_from_url

    return await fetch_blueprint_from_url(
        hass, BLUEPRINT_URL.format(version=BLUEPRINT_VERSION)
    )


async def async_install_blueprint(hass: HomeAssistant) -> str:
    """Install the blueprint for a house that has none.

    `allow_override=False`: this path exists only for the no-blueprint
    case, and if something did appear at that path between the check and
    the user pressing Fix, overwriting it silently would be the wrong
    answer - updating is what the other repair is for.
    """
    imported = await _fetch(hass)
    await async_get_blueprints(hass).async_add_blueprint(
        imported.blueprint, INSTALL_PATH, allow_override=False
    )
    return INSTALL_PATH


async def async_update_blueprints(hass: HomeAssistant) -> list[str]:
    """Overwrite every stale in-use copy with the shipped version.

    Fetched once and written to each path we found it at, so a house
    that ended up with the blueprint at two paths (see the module
    docstring) has both corrected rather than only the one Home
    Assistant would pick by itself. async_add_blueprint reloads the
    automations using each path for us.
    """
    outdated = await outdated_blueprints(hass)
    if not outdated:
        return []

    imported = await _fetch(hass)
    domain_blueprints = async_get_blueprints(hass)

    updated = []
    for stale in outdated:
        await domain_blueprints.async_add_blueprint(
            imported.blueprint, stale.path, allow_override=True
        )
        updated.append(stale.path)
    return updated
