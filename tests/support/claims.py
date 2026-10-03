"""Reading one field of a light's claim back out of the ClaimRegistry."""

from typing import Any, Optional


def claim_field(registry, zone: Optional[str], entity_id: str, claim: str, field: str) -> Any:
    """`field` of the light's `claim` ("observed" or "latest"), or None."""
    record = registry.record(zone, entity_id) or {}
    return (record.get(claim) or {}).get(field)
