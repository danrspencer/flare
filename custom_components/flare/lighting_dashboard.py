"""FLARE's dashboard: a Lovelace dashboard made by the `custom:flare`
strategy, so its views follow the schedules and zones as they change.

Made the way HA makes its own Map dashboard (`_create_map_dashboard` in
`components/lovelace/__init__.py`): an item in the dashboards collection,
then its config saved. HA keeps the collection private to lovelace's
setup; the websocket command that creates dashboards holds it, which is
how it's reached here; test_area_setup.py runs it against the real
lovelace, so a change in HA breaks a test rather than setup."""

from __future__ import annotations

import inspect

from homeassistant.components import websocket_api
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant

URL_PATH = "flare"
TITLE = "Lighting"
ICON = "flare:logo"
CONFIG = {"strategy": {"type": "custom:flare"}}


def dashboard_exists(hass: HomeAssistant) -> bool:
    data = hass.data.get(LOVELACE_DATA)
    return bool(data and URL_PATH in data.dashboards)


async def async_create_dashboard(hass: HomeAssistant) -> None:
    handler, _ = hass.data[websocket_api.DOMAIN]["lovelace/dashboards/create"]
    collection = inspect.unwrap(handler).__self__.storage_collection
    await collection.async_create_item(
        {"title": TITLE, "icon": ICON, "url_path": URL_PATH, "allow_single_word": True}
    )
    await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_save(CONFIG)
