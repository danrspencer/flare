"""
The front-end files are served from a versioned URL.

`cache_headers=False` was the previous approach and does not mean "do not
cache": it omits Cache-Control but leaves ETag and Last-Modified, so a
browser may cache heuristically - which it did, serving a stale card
after a deploy until the window lapsed. A version in the path makes every
release a new URL, so that cannot happen, and caching hard becomes
correct rather than merely tolerable.

A development build has the same placeholder version for every commit, so
there the URL follows the files' content instead - otherwise the cache
bug this replaced would come straight back for anyone running dev.
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.flare import _content_version, async_setup

COMPONENT = Path(__file__).resolve().parent.parent.parent / "custom_components" / "flare"


async def _register(hass, *, version=None):
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    with patch("custom_components.flare.add_extra_js_url") as add_js:
        if version is None:
            assert await async_setup(hass, {})
        else:
            with patch(
                "custom_components.flare.async_get_integration",
                AsyncMock(return_value=MagicMock(version=version)),
            ):
                assert await async_setup(hass, {})

    (configs,), _ = hass.http.async_register_static_paths.call_args
    assert len(configs) == 1, "one static path serves the whole directory"
    return configs[0], [call.args[1] for call in add_js.call_args_list]


async def test_the_served_url_carries_the_integration_version(hass):
    config, served = await _register(hass, version="0.17.0")

    assert config.url_path == "/flare_static/0.17.0"
    assert config.cache_headers is True

    assert served, "no front-end files were registered with the frontend"
    for url in served:
        assert url.startswith("/flare_static/0.17.0/"), url
        # add_extra_js_url takes any string; a stale name is a 404 the
        # browser reports and nothing else does.
        assert (COMPONENT / "www" / url.rsplit("/", 1)[-1]).is_file(), url


async def test_a_development_build_is_served_from_a_url_that_follows_its_content(hass):
    """The source's manifest version is the placeholder, so this is what
    running from the dev branch looks like."""
    config, served = await _register(hass)

    assert re.fullmatch(r"/flare_static/dev-[0-9a-f]{10}", config.url_path), config.url_path
    assert config.cache_headers is True
    assert all(url.startswith(config.url_path + "/") for url in served)


def test_the_content_version_changes_when_a_served_file_does(tmp_path):
    (tmp_path / "card.js").write_text("one")
    before = _content_version(tmp_path)

    assert _content_version(tmp_path) == before, "not stable between calls"

    (tmp_path / "card.js").write_text("two")
    assert _content_version(tmp_path) != before
