"""Entity-registry entries as the front end sees them (`hass.entities`),
for FLARE's schedules and zones under their usual entity IDs."""

from custom_components.flare.schedule.coordinator import CURVE_KEYS, TIME_KEYS


def flare_entities(device_id: str, roles: dict[str, str]) -> dict[str, dict]:
    """One device's entities: {role: entity_id} as registry entries."""
    return {
        entity_id: {"entity_id": entity_id, "device_id": device_id, "platform": "flare", "translation_key": role}
        for role, entity_id in roles.items()
    }


def schedule_entities(device_id: str, slug: str) -> dict[str, dict]:
    roles = {
        "schedule": f"sensor.{slug}_flare",
        "phase_override": f"select.{slug}_flare_phase",
        "sticky_phase_override": f"switch.{slug}_sticky_phase_override",
        **{key: f"time.{slug}_{key}" for key in TIME_KEYS},
        **{key: f"number.{slug}_{key}" for key in CURVE_KEYS},
    }
    return flare_entities(device_id, roles)


def zone_entities(device_id: str, slug: str) -> dict[str, dict]:
    roles = {
        "claims": f"sensor.{slug}_flare_claims",
        "controlled": f"sensor.{slug}_flare_controlled",
        "overridden": f"sensor.{slug}_flare_overridden",
        "clear": f"button.{slug}_flare_clear",
    }
    return flare_entities(device_id, roles)
