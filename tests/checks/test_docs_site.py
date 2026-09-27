"""The docs site's source pages. Both failures here are silent: the site
builds and the page is simply wrong.

1. Without front matter, Jekyll copies a page through as raw Markdown.
2. Liquid shares {{ }} with Home Assistant Jinja and renders unknown
   filters as nothing, so a page documenting Jinja must set
   render_with_liquid: false - and then can't use relative_url.
"""

import re
from pathlib import Path

import pytest

from tests.support import BLUEPRINT_FILE, REPO_ROOT

DOCS = REPO_ROOT / "docs"
# Build output and generated pages, not source pages.
_BUILD_DIRS = {
    "_site",
    "_preview",
    "_build",
    "vendor",
    "_includes",
    "trace-report",  # scripts/trace_viewer.py --export, deliberately unthemed
}
PAGES = sorted(
    p
    for p in list(DOCS.rglob("*.md")) + list(DOCS.rglob("*.html"))
    if not _BUILD_DIRS.intersection(p.relative_to(DOCS).parts)
)


def _front_matter(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, _, rest = text.partition("---\n")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    values = {}
    for line in block.splitlines():
        if line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        values[key.strip()] = value.strip()
    return values


def test_there_are_pages_to_check():
    assert len(PAGES) >= 5, f"expected the site's pages, found {[p.name for p in PAGES]}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_has_front_matter_with_a_title(page):
    front = _front_matter(page)
    assert front, (
        f"{page.name} has no front matter block, so Jekyll will copy it through as a static "
        "file instead of rendering it as a page"
    )
    assert "title" in front, f"{page.name} has front matter but no title, so it has no name in the nav"


LIQUID_EXPRESSION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
# The Liquid this site uses; anything else in {{ }} is documented Jinja.
SITE_LIQUID = ("relative_url", "site.", "page.")


def _expressions(page: Path) -> list[str]:
    body = page.read_text(encoding="utf-8").split("\n---", 1)[-1]
    return [m.group(1) for m in LIQUID_EXPRESSION.finditer(body)]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_documenting_jinja_disable_liquid(page):
    jinja = [e for e in _expressions(page) if not any(marker in e for marker in SITE_LIQUID)]
    if not jinja:
        return
    front = _front_matter(page)
    assert front.get("render_with_liquid") == "false", (
        f"{page.name} documents Jinja ({jinja[0].strip()[:40]!r}) but doesn't set "
        "render_with_liquid: false - Liquid will evaluate it and publish an empty string"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_liquid_free_pages_dont_use_liquid_filters(page):
    """With Liquid off, relative_url publishes as literal text."""
    if _front_matter(page).get("render_with_liquid") != "false":
        return
    used = [e for e in _expressions(page) if any(marker in e for marker in SITE_LIQUID)]
    assert not used, (
        f"{page.name} has Liquid disabled, so {used[0].strip()[:40]!r} won't be evaluated - "
        "use a plain relative path"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_page_links_to_a_markdown_file(page):
    """A link to a sibling .md file is a 404 on the site."""
    body = page.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", body)
    stale = [t for t in targets if ".md" in t and "github.com" not in t]
    assert not stale, f"{page.name} links to Markdown files that aren't published: {stale[:5]}"


# --- Inbound links to the blueprint reference ---------------------------


def test_every_referenced_blueprint_anchor_exists():
    """The blueprint's input descriptions and the blueprint test classes
    deep-link into docs/blueprint.md, so renaming a heading breaks them.
    Anchors are derived the way kramdown does it."""
    page = (DOCS / "blueprint.md").read_text()

    def slug(heading: str) -> str:
        # kramdown: drop non-word characters, spaces to hyphens, runs kept.
        return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", heading.lower()).strip())

    have = {slug(m) for m in re.findall(r"^#{2,3} (.+)$", page, re.MULTILINE)}
    sources = [BLUEPRINT_FILE, *(REPO_ROOT / "tests" / "functional" / "blueprint").glob("test_*.py")]
    referenced = {a for path in sources for a in re.findall(r"blueprint(?:/|\.md)#([a-z0-9-]+)", path.read_text())}

    assert referenced, "found no inbound links at all - has the link shape changed?"
    assert referenced <= have, f"dead anchors in docs/blueprint.md: {sorted(referenced - have)}"
