"""The front-end files are served from a URL carrying a fingerprint of
them, cached hard."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.flare import async_setup, www_fingerprint
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
    assert served, "no front-end files were registered with the frontend"
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
