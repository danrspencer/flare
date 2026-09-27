"""Fix flows for blueprint_check.py's repairs. HA finds this module by
name."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .blueprint_check import ISSUE_ID as BLUEPRINT_ISSUE_ID
from .blueprint_check import MISSING_ISSUE_ID as BLUEPRINT_MISSING_ISSUE_ID
from .blueprint_check import async_install_blueprint
from .blueprint_check import async_update_blueprints, describe as describe_blueprints, outdated_blueprints
from .blueprint_version import BLUEPRINT_VERSION


class OutdatedBlueprintRepairFlow(RepairsFlow):
    """Re-imports this release's blueprint over the installed one, after
    confirmation, since the user may have edited it."""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        if user_input is not None:
            try:
                updated = await async_update_blueprints(self.hass)
            except Exception:  # noqa: BLE001
                # A GitHub fetch; aborting leaves the repair to retry.
                return self.async_abort(reason="update_failed")
            return self.async_create_entry(title="", data={"updated": updated})

        outdated = await outdated_blueprints(self.hass)
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "current": BLUEPRINT_VERSION,
                "blueprints": describe_blueprints(outdated),
            },
        )


class MissingBlueprintRepairFlow(RepairsFlow):
    """Installs the blueprint for a house that has none."""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        if user_input is not None:
            try:
                path = await async_install_blueprint(self.hass)
            except Exception:  # noqa: BLE001
                # A GitHub fetch; aborting leaves the repair to retry.
                return self.async_abort(reason="install_failed")
            return self.async_create_entry(title="", data={"installed": path})

        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Called by Home Assistant when the user presses Fix on our issue."""
    entries = hass.config_entries.async_entries(DOMAIN)
    entry_id = entries[0].entry_id if entries else ""
    if issue_id == BLUEPRINT_ISSUE_ID:
        return OutdatedBlueprintRepairFlow()
    if issue_id == BLUEPRINT_MISSING_ISSUE_ID:
        return MissingBlueprintRepairFlow()
    raise ValueError(f"Unknown repair issue for {DOMAIN}: {issue_id}")
