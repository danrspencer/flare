"""Whether a schedule's or flare's name is free. Entity IDs are made from
the name's slug, so two names are the same when their slugs are."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import slugify


def name_taken(entry: ConfigEntry, name: str, skip: str | None = None) -> bool:
    """True if one of the entry's subentries, other than `skip`, has a name
    with the same slug."""
    slug = slugify(name)
    return any(
        slugify(subentry.title) == slug for subentry_id, subentry in entry.subentries.items() if subentry_id != skip
    )
