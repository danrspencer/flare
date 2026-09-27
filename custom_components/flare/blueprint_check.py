"""Raises a repair when the blueprint is missing or older than this
release's, and installs or updates it on Fix.

Only blueprints an automation uses count as outdated: a GitHub import
lands under the repo owner's name (`danrspencer/`), not this repo's
folder (`danspencer/`), so an orphaned copy can sit at the other path
forever."""

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

# HA derives the install path from the GitHub URL's owner (`danrspencer`),
# so a hand import by URL overwrites this file rather than duplicating it.
INSTALL_PATH = "danrspencer/flare.yaml"

QUICKSTART_URL = "https://danrspencer.github.io/flare/installation/"

# A tag, not `main`: a branch raw URL can be served stale after a push.
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
    """By name or by source_url, since an edited copy may have lost either."""
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
    # Blueprints that failed to load come back as the exception.
    return {
        path: bp
        for path, bp in installed.items()
        if isinstance(bp, Blueprint) and _is_ours(bp)
    }


async def blueprint_is_installed(hass: HomeAssistant) -> bool:
    """In use or not - an unused one means setup is in progress."""
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
    """Raise whichever of the two blueprint repairs applies, clearing the other."""
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
    """The shipped blueprint, from this release's tag."""
    from homeassistant.components.blueprint.importer import fetch_blueprint_from_url

    return await fetch_blueprint_from_url(
        hass, BLUEPRINT_URL.format(version=BLUEPRINT_VERSION)
    )


async def async_install_blueprint(hass: HomeAssistant) -> str:
    """Install the blueprint for a house that has none. Never overwrites."""
    imported = await _fetch(hass)
    await async_get_blueprints(hass).async_add_blueprint(
        imported.blueprint, INSTALL_PATH, allow_override=False
    )
    return INSTALL_PATH


async def async_update_blueprints(hass: HomeAssistant) -> list[str]:
    """Overwrite every stale in-use copy, at whatever path it was found."""
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
