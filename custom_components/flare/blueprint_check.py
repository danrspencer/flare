"""Raises a repair when the blueprint is missing, older than this
release's or in another language than Home Assistant's, and installs or
updates it on Fix.

Only blueprints an automation uses count as outdated: HA never removes
an unused copy, so one left at another path would otherwise nag
forever."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.components.automation import automations_with_blueprint
from homeassistant.components.automation.helpers import async_get_blueprints
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.const import CONF_DESCRIPTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import yaml as yaml_util

from .blueprint_translation import ENGLISH, TRANSLATIONS, language_for, translate
from .blueprint_version import (
    BLUEPRINT_VERSION,
    is_outdated,
    language_from_description,
    version_from_description,
)
from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)

ISSUE_ID = "outdated_blueprint"
MISSING_ISSUE_ID = "blueprint_not_installed"

# Under blueprints/automation/.
INSTALL_PATH = "flare/flare.yaml"

# The blueprint this release ships, installed and updated from here.
SHIPPED_BLUEPRINT = Path(__file__).parent / "blueprints" / "flare.yaml"

QUICKSTART_URL = "https://danrspencer.github.io/flare/installation/"

_OUR_NAME = NAME


@dataclass(frozen=True)
class InstalledBlueprint:
    """One copy of our blueprint that some automation is using."""

    path: str  # as Home Assistant knows it, e.g. "flare/flare.yaml"
    version: str | None  # None for anything released before the stamp existed
    language: str | None  # None for anything stamped before copies carried it
    automations: int


def _is_ours(blueprint: Blueprint) -> bool:
    return blueprint.name == _OUR_NAME


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


async def automations_using_our_blueprint(hass: HomeAssistant) -> list[str]:
    """Every automation built from any copy of our blueprint."""
    return sorted({a for path in await _ours(hass) for a in automations_with_blueprint(hass, path)})


async def outdated_blueprints(hass: HomeAssistant) -> list[InstalledBlueprint]:
    """Every copy of our blueprint that is in use and out of date, or in
    a language other than Home Assistant's."""
    installed = await _ours(hass)
    wanted = await _language(hass)

    outdated = []
    for path, blueprint in installed.items():
        using = automations_with_blueprint(hass, path)
        if not using:
            continue
        description = blueprint.metadata.get(CONF_DESCRIPTION)
        version = version_from_description(description)
        language = language_from_description(description)
        if is_outdated(version) or (language or ENGLISH) != wanted:
            outdated.append(InstalledBlueprint(path, version, language, len(using)))
    return outdated


def describe(blueprints: list[InstalledBlueprint]) -> str:
    """Markdown for the issue and the confirm step."""
    return "\n".join(
        f"- `{b.path}` — version {b.version or 'unknown'}{f' ({b.language})' if b.language else ''}, "
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


def _available_languages() -> list[str]:
    return [path.stem for path in TRANSLATIONS.glob("*.yaml")]


async def _language(hass: HomeAssistant) -> str:
    """The language our blueprint should be written in: Home Assistant's,
    if there's a table for it."""
    available = await hass.async_add_executor_job(_available_languages)
    return language_for(hass.config.language, available)


def _load_shipped(language: str) -> dict:
    data = yaml_util.load_yaml_dict(SHIPPED_BLUEPRINT)
    table = None if language == ENGLISH else yaml_util.load_yaml_dict(TRANSLATIONS / f"{language}.yaml")
    return translate(data, table, language)


async def _shipped(hass: HomeAssistant) -> Blueprint:
    """The blueprint packaged with this release, in Home Assistant's language."""
    data = await hass.async_add_executor_job(_load_shipped, await _language(hass))
    return Blueprint(data, expected_domain=AUTOMATION_DOMAIN, schema=BLUEPRINT_SCHEMA)


async def async_install_blueprint(hass: HomeAssistant) -> str:
    """Install the blueprint for a house that has none. Never overwrites."""
    await async_get_blueprints(hass).async_add_blueprint(
        await _shipped(hass), INSTALL_PATH, allow_override=False
    )
    return INSTALL_PATH


async def async_blueprint_path(hass: HomeAssistant) -> str:
    """The path new automations should use: INSTALL_PATH if a copy is
    there, otherwise any copy of ours, otherwise a fresh install."""
    installed = await _ours(hass)
    if INSTALL_PATH in installed or not installed:
        if not installed:
            await async_install_blueprint(hass)
            await async_check(hass)
        return INSTALL_PATH
    return sorted(installed)[0]


async def async_update_blueprints(hass: HomeAssistant) -> list[str]:
    """Overwrite every stale in-use copy, at whatever path it was found."""
    outdated = await outdated_blueprints(hass)
    if not outdated:
        return []

    shipped = await _shipped(hass)
    domain_blueprints = async_get_blueprints(hass)

    updated = []
    for stale in outdated:
        await domain_blueprints.async_add_blueprint(
            shipped, stale.path, allow_override=True
        )
        updated.append(stale.path)
    return updated
