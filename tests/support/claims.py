"""Reading one field of a light's claim back out of the ClaimRegistry."""

from typing import Any


def claim_field(registry, entity_id: str, claim: str, field: str) -> Any:
    """`field` of the light's `claim` ("observed" or "latest"), or None."""
    record = registry.record(entity_id) or {}
    return (record.get(claim) or {}).get(field)


def after_the_grace():
    """A frozen clock past MISMATCH_GRACE, so a mismatch noted now reads as
    an override."""
    from datetime import timedelta

    from freezegun import freeze_time
    from homeassistant.util import dt as dt_util

    from custom_components.flare.tracking.override_protection import MISMATCH_GRACE

    return freeze_time(dt_util.utcnow() + MISMATCH_GRACE + timedelta(seconds=1), real_asyncio=True)
