"""flare.resolve_target: the entities a target reaches, by Home Assistant's
own rule (helpers/target.py) - the one `light.turn_on area_id:` and a
flare's membership use. Templates can't apply it: they can't see an
entity's category.

Registered once for the domain, not by either entry: it needs nothing of
FLARE's."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.target import TargetSelection, async_extract_referenced_entity_ids

from ..const import DOMAIN

RESOLVE_TARGET_SCHEMA = vol.Schema(cv.TARGET_FIELDS)


def async_setup_target_services(hass: HomeAssistant) -> None:
    async def resolve_target(call: ServiceCall) -> ServiceResponse:
        """flare.resolve_target - see services.yaml."""
        # expand_group=False, as a flare's tracker resolves its room.
        selected = async_extract_referenced_entity_ids(hass, TargetSelection(call.data), expand_group=False)
        return {"entities": sorted(selected.referenced | selected.indirectly_referenced)}

    hass.services.async_register(
        DOMAIN,
        "resolve_target",
        resolve_target,
        schema=RESOLVE_TARGET_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
