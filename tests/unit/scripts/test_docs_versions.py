"""scripts/docs_site.py: where each version's docs land in the published
site, and which versions the picker offers."""

import json
from pathlib import Path

import pytest

from tests.support import load_script

docs_site = load_script("docs_site")


def _build(root: Path, name: str, *, trace_report: bool = False) -> Path:
    """A built site whose pages say which build they came from."""
    build = root / name
    (build / "installation").mkdir(parents=True)
    page = f"<html><head><title>{name}</title></head><body>{name}</body></html>"
    (build / "index.html").write_text(page)
    (build / "installation" / "index.html").write_text(page)
    if trace_report:
        (build / "trace-report").mkdir()
        (build / "trace-report" / "index.html").write_text(f"<html><head></head>trace {name}</html>")
    return build


def _publish(site: Path, tmp_path: Path, channel: str, version: str, **kw) -> bool:
    return docs_site.publish(
        site,
        channel,
        version,
        _build(tmp_path / "builds" / version, "version", **kw),
        _build(tmp_path / "builds" / version, "root", **kw),
    )


def _body(path: Path) -> str:
    return path.read_text().split("<body>")[-1].split("</body>")[0]


def _versions(site: Path) -> dict:
    return json.loads((site / "_versions" / "versions.json").read_text())


@pytest.fixture
def site(tmp_path):
    return tmp_path / "site"


def test_before_any_release_the_beta_is_also_the_default(site, tmp_path):
    _publish(site, tmp_path, "beta", "1.0.0-beta.13")

    assert _body(site / "index.html") == "root"
    assert _body(site / "beta" / "index.html") == "version"
    assert _versions(site) == {"latest": "1.0.0-beta.13", "releases": [], "beta": "1.0.0-beta.13"}


def test_a_release_becomes_the_default_and_keeps_its_own_path(site, tmp_path):
    _publish(site, tmp_path, "beta", "1.0.0-beta.13")
    _publish(site, tmp_path, "release", "1.0.0")

    assert _body(site / "index.html") == "root"
    assert _body(site / "v" / "1.0.0" / "installation" / "index.html") == "version"
    assert _versions(site) == {"latest": "1.0.0", "releases": ["1.0.0"], "beta": None}
    assert not (site / "beta").exists(), "its beta is the release now"


def test_every_release_is_kept_newest_first(site, tmp_path):
    for version in ("1.0.0", "1.1.0", "1.0.1"):
        _publish(site, tmp_path, "release", version)

    assert _versions(site)["releases"] == ["1.1.0", "1.0.1", "1.0.0"]
    assert all((site / "v" / v).is_dir() for v in ("1.0.0", "1.0.1", "1.1.0"))


def test_an_older_release_published_late_does_not_take_the_root(site, tmp_path):
    _publish(site, tmp_path, "release", "1.1.0")
    (site / "index.html").write_text("<html><head></head><body>1.1.0 root</body></html>")
    _publish(site, tmp_path, "release", "1.0.1")

    assert _body(site / "index.html") == "1.1.0 root"
    assert _versions(site)["latest"] == "1.1.0"


def test_a_beta_newer_than_the_release_is_offered_but_not_the_default(site, tmp_path):
    _publish(site, tmp_path, "release", "1.0.0")
    (site / "index.html").write_text("<html><head></head><body>release root</body></html>")
    _publish(site, tmp_path, "beta", "1.1.0-beta.1")

    assert _body(site / "index.html") == "release root"
    assert _body(site / "beta" / "index.html") == "version"
    assert _versions(site) == {"latest": "1.0.0", "releases": ["1.0.0"], "beta": "1.1.0-beta.1"}


def test_the_next_beta_replaces_the_last(site, tmp_path):
    _publish(site, tmp_path, "release", "1.0.0")
    _publish(site, tmp_path, "beta", "1.1.0-beta.1")
    (site / "beta" / "gone.html").write_text("old")
    _publish(site, tmp_path, "beta", "1.1.0-beta.2")

    assert not (site / "beta" / "gone.html").exists()
    assert _versions(site)["beta"] == "1.1.0-beta.2"


def test_a_beta_no_newer_than_the_release_is_not_published(site, tmp_path):
    """A docs-only push after a release, before the next beta."""
    _publish(site, tmp_path, "release", "1.0.0")

    assert _publish(site, tmp_path, "beta", "1.0.0-beta.13") is False
    assert not (site / "beta").exists()
    assert _versions(site)["beta"] is None


def test_a_release_leaves_the_other_versions_alone(site, tmp_path):
    _publish(site, tmp_path, "release", "1.0.0")
    _publish(site, tmp_path, "beta", "1.1.0-beta.1", trace_report=True)
    _publish(site, tmp_path, "release", "1.0.1")

    assert (site / "v" / "1.0.0").is_dir()
    assert (site / "beta").is_dir()
    assert (site / "trace-report" / "index.html").is_file()


def test_the_trace_report_comes_from_the_beta_and_sits_at_the_root(site, tmp_path):
    _publish(site, tmp_path, "release", "1.0.0")
    _publish(site, tmp_path, "beta", "1.1.0-beta.1", trace_report=True)

    assert "trace version" in (site / "trace-report" / "index.html").read_text()
    assert not (site / "beta" / "trace-report").exists()


def test_every_page_loads_the_picker_once(site, tmp_path):
    _publish(site, tmp_path, "release", "1.0.0")
    _publish(site, tmp_path, "beta", "1.1.0-beta.1", trace_report=True)

    tag = '<script defer src="/flare/_versions/picker.js"></script>'
    for page in ("index.html", "v/1.0.0/index.html", "beta/installation/index.html"):
        assert (site / page).read_text().count(tag) == 1, page
    assert "picker.js" not in (site / "trace-report" / "index.html").read_text()
    assert (site / "_versions" / "picker.js").read_text() == docs_site.PICKER_SOURCE.read_text()


def test_the_newest_beta_tag_is_the_betas_version():
    assert docs_site.latest_beta(["v1.0.0-beta.9", "v1.0.0-beta.13", "v0.9.0", "junk"]) == "1.0.0-beta.13"
    assert docs_site.latest_beta(["v0.9.0"]) is None
