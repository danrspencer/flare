"""Getting FLARE's dashboard into a page that was open while FLARE was
first set up.

The frontend loads integrations' modules only from the page it was served,
so that page never offers the FLARE Lighting dashboard. First setup links
to a reload and raises a repair saying so; the beacon, one of the modules
every freshly served page loads, clears it."""

from __future__ import annotations

import uuid
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

ISSUE_ID = "reload_for_dashboard"
# Not under /api/, where HA rejects a request carrying an Origin it doesn't
# list, as a module import always does. www/flare-loader.js imports it.
BEACON_URL = "/flare_static/frontend_loaded.js"
DASHBOARDS_PATH = "/config/lovelace/dashboards"


def reload_link() -> str:
    """A link that reloads the page instead of navigating within it
    (`target`), to a URL the service worker has never cached (the token),
    so the page comes fresh from Home Assistant."""
    return f'<a href="{DASHBOARDS_PATH}?flare_reload={uuid.uuid4().hex[:8]}" target="_self">Reload this page</a>'


@callback
def async_raise(hass: HomeAssistant, link: str) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        translation_placeholders={"reload": link},
    )


class StaleFilesView(HomeAssistantView):
    """www/ under any fingerprint but the current one, which its static
    path serves first. A page served before an update still asks for the
    old one, and would otherwise get no dashboard at all. Not cached, so an
    old URL never keeps today's files."""

    url = "/flare_static/{fingerprint}/{path:.+}"
    name = "flare:stale_files"
    requires_auth = False

    def __init__(self, www: Path) -> None:
        self._www = www.resolve()

    async def get(self, request: web.Request, fingerprint: str, path: str) -> web.StreamResponse:
        file = (self._www / path).resolve()
        if not file.is_relative_to(self._www) or not await request.app[KEY_HASS].async_add_executor_job(file.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(file, headers={"Cache-Control": "no-cache"})


class FrontendLoadedView(HomeAssistantView):
    """An empty module, so its request means a page has loaded FLARE's
    front end. Module scripts are fetched without credentials, hence no
    auth; all it can do is clear the reminder."""

    url = BEACON_URL
    name = "api:flare:frontend_loaded"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        ir.async_delete_issue(request.app[KEY_HASS], DOMAIN, ISSUE_ID)
        return web.Response(text="", content_type="text/javascript", headers={"Cache-Control": "no-store"})
