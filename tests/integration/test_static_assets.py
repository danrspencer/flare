"""
The front-end files are served from a versioned URL.

`cache_headers=False` was the previous approach and does not mean "do not
cache": it omits Cache-Control but leaves ETag and Last-Modified, so a
browser may cache heuristically - which it did, serving a stale card
after a deploy until the window lapsed. A version in the path makes every
release a new URL, so that cannot happen, and caching hard becomes
correct rather than merely tolerable.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.flare import async_setup

COMPONENT = Path(__file__).resolve().parent.parent.parent / "custom_components" / "flare"


async def test_the_served_url_carries_the_integration_version(hass):
    version = json.loads((COMPONENT / "manifest.json").read_text())["version"]

    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    with patch("custom_components.flare.add_extra_js_url") as add_js:
        assert await async_setup(hass, {})

    (configs,), _ = hass.http.async_register_static_paths.call_args
    assert len(configs) == 1, "one static path serves the whole directory"
    assert configs[0].url_path == f"/flare_static/{version}"
    assert configs[0].cache_headers is True

    served = [call.args[1] for call in add_js.call_args_list]
    assert served, "no front-end files were registered with the frontend"
    for url in served:
        assert url.startswith(f"/flare_static/{version}/"), url
        # add_extra_js_url takes any string; a stale name is a 404 the
        # browser reports and nothing else does.
        assert (COMPONENT / "www" / url.rsplit("/", 1)[-1]).is_file(), url
