"""The front-end files are served from a versioned URL, cached hard."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.flare import async_setup
from tests.support import COMPONENT


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
        # A missing file is only ever a 404 in the browser.
        assert (COMPONENT / "www" / url.rsplit("/", 1)[-1]).is_file(), url
