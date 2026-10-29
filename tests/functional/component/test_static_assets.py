"""The front-end files are served from a URL carrying a fingerprint of
them, cached hard. An older fingerprint still serves them, uncached."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from homeassistant.components.http import KEY_HASS

from custom_components.flare import async_setup, www_fingerprint
from custom_components.flare.dashboard_reload import StaleFilesView
from tests.support import COMPONENT, WWW


async def test_the_served_url_carries_a_fingerprint_of_the_files(hass):
    fingerprint = www_fingerprint(WWW)

    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    with patch("custom_components.flare.add_extra_js_url") as add_js:
        assert await async_setup(hass, {})

    (configs,), _ = hass.http.async_register_static_paths.call_args
    assert len(configs) == 1, "one static path serves the whole directory"
    assert configs[0].url_path == f"/flare_static/{fingerprint}"
    assert configs[0].cache_headers is True

    served = [call.args[1] for call in add_js.call_args_list]
    assert served == [f"/flare_static/{fingerprint}/flare-loader.js"], "the loader is the one entry point"
    for url in served:
        assert url.startswith(f"/flare_static/{fingerprint}/"), url
        # A missing file is only ever a 404 in the browser.
        assert (COMPONENT / "www" / url.rsplit("/", 1)[-1]).is_file(), url


def test_changing_any_file_changes_the_fingerprint(tmp_path):
    """Including a dev build, whose version never changes."""
    (tmp_path / "a.js").write_text("one")
    (tmp_path / "b.js").write_text("two")
    before = www_fingerprint(tmp_path)

    assert www_fingerprint(tmp_path) == before
    (tmp_path / "b.js").write_text("two!")
    assert www_fingerprint(tmp_path) != before


def test_renaming_a_file_changes_the_fingerprint(tmp_path):
    (tmp_path / "a.js").write_text("same")
    before = www_fingerprint(tmp_path)

    (tmp_path / "a.js").rename(tmp_path / "b.js")

    assert www_fingerprint(tmp_path) != before


def test_the_loader_imports_the_beacon_the_server_serves():
    from custom_components.flare.dashboard_reload import BEACON_URL

    assert f"'{BEACON_URL}'" in (WWW / "flare-loader.js").read_text()


def test_every_module_that_registers_something_is_loaded():
    """Reached from the loader, directly or through another module's imports."""
    import re

    imports = re.compile(r"""import\b[^'"\n]*['"]\./([^'"]+)['"]""")
    registers = re.compile(r"customElements\.define|window\.custom\w+")
    reached, todo = set(), ["flare-loader.js"]
    while todo:
        name = todo.pop()
        if name not in reached:
            reached.add(name)
            todo += imports.findall((WWW / name).read_text())
    registering = {p.name for p in WWW.glob("*.js") if registers.search(p.read_text())}
    assert registering - reached == set()


async def _serve_www(hass, hass_client_no_auth):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "http", {})
    with patch("custom_components.flare.add_extra_js_url"):
        assert await async_setup(hass, {})
    return await hass_client_no_auth()


async def test_a_page_from_before_an_update_still_gets_the_files(hass, hass_client_no_auth):
    """It asks for the previous fingerprint, which nothing else serves."""
    client = await _serve_www(hass, hass_client_no_auth)

    for path in ("flare-loader.js", "flare-view-strategy.js"):
        response = await client.get(f"/flare_static/0123456789ab/{path}")
        assert response.status == 200, path
        assert await response.read() == (WWW / path).read_bytes(), path
        assert "javascript" in response.content_type, path
        assert response.headers["Cache-Control"] == "no-cache", "an old URL never keeps today's files"


async def test_the_current_fingerprint_is_still_cached_hard(hass, hass_client_no_auth):
    client = await _serve_www(hass, hass_client_no_auth)

    response = await client.get(f"/flare_static/{www_fingerprint(WWW)}/flare-loader.js")

    assert response.status == 200
    assert "no-cache" not in response.headers.get("Cache-Control", "")


async def test_an_old_fingerprint_serves_nothing_outside_www(hass, hass_client_no_auth):
    client = await _serve_www(hass, hass_client_no_auth)

    assert (await client.get("/flare_static/0123456789ab/missing.js")).status == 404
    for path in ("..%2F__init__.py", "../manifest.json"):
        assert (await client.get(f"/flare_static/0123456789ab/{path}")).status in (400, 404), path

    # Past Home Assistant's own filtering too.
    request = MagicMock()
    request.app = {KEY_HASS: hass}
    with pytest.raises(web.HTTPNotFound):
        await StaleFilesView(WWW).get(request, "0123456789ab", "../__init__.py")
