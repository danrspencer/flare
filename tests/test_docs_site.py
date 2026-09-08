"""
Guards the documentation site's source pages.

Everything except README.md lives in docs/ and is published to GitHub
Pages. Two of the ways that breaks are silent - the site builds happily
and the page is simply wrong - so they're pinned here rather than left to
be noticed by a reader:

1. A page with no front matter is not a page. Jekyll only *renders* a
   file that has a literal front matter block; anything else is treated
   as a static file and copied through verbatim, so the published URL
   serves raw Markdown with no theme, no nav and no title. Front matter
   defaults in _config.yml do not help - they merge into pages, they
   don't promote a static file into one.

2. Liquid eats Home Assistant Jinja. Both share the {{ }} delimiters, and
   Jekyll's default lax filter handling renders an unknown filter as an
   empty string - so a documented `{{ today_at('06:00:00') | as_timestamp }}`
   publishes as a blank line, with no build error. Pages carrying Jinja
   must set render_with_liquid: false, and having done so they can no
   longer use Liquid's relative_url filter either.
"""

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs"
# Recursive: pages live in subdirectories too (docs/advanced/), and a
# top-level-only glob quietly stopped guarding them the moment the site
# grew a section. Jekyll's own build directories aren't source pages.
_BUILD_DIRS = {"_site", "_preview", "_build", "vendor", "_includes"}
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
    """Guards against this whole file silently passing over an empty
    glob if docs/ is ever restructured."""
    assert len(PAGES) >= 5, f"expected the site's pages, found {[p.name for p in PAGES]}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_has_front_matter_with_a_title(page):
    front = _front_matter(page)
    assert front, (
        f"{page.name} has no front matter block, so Jekyll will copy it through as a static "
        "file instead of rendering it as a page"
    )
    assert "title" in front, f"{page.name} has front matter but no title, so it has no name in the nav"


# {{ ... }} means two different things across this site, and telling
# them apart is the whole point of the two tests below. A page either
# uses Liquid deliberately (the site's own `relative_url` links) or it
# documents Home Assistant Jinja, which happens to share the delimiters.
# It cannot do both: turning Liquid off to protect the Jinja also turns
# off relative_url.
LIQUID_EXPRESSION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
# The Liquid this site actually uses. Anything else inside {{ }} is
# assumed to be Home Assistant Jinja being documented.
SITE_LIQUID = ("relative_url", "site.", "page.")


def _expressions(page: Path) -> list[str]:
    body = page.read_text(encoding="utf-8").split("\n---", 1)[-1]
    return [m.group(1) for m in LIQUID_EXPRESSION.finditer(body)]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_documenting_jinja_disable_liquid(page):
    """The failure this prevents is invisible: the page builds, and the
    Jinja example publishes as an empty string."""
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
    """The other half of the same rule: with Liquid off, a relative_url
    filter publishes as literal text instead of a link. Checks real
    {{ ... }} usage, not the word appearing in prose."""
    if _front_matter(page).get("render_with_liquid") != "false":
        return
    used = [e for e in _expressions(page) if any(marker in e for marker in SITE_LIQUID)]
    assert not used, (
        f"{page.name} has Liquid disabled, so {used[0].strip()[:40]!r} won't be evaluated - "
        "use a plain relative path"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_page_links_to_a_markdown_file(page):
    """These pages used to be read on GitHub and linked to each other as
    sibling .md files. On the site those are 404s."""
    body = page.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", body)
    stale = [t for t in targets if ".md" in t and "github.com" not in t]
    assert not stale, f"{page.name} links to Markdown files that aren't published: {stale[:5]}"


# --- Inbound links to the blueprint reference ---------------------------


def test_every_referenced_blueprint_anchor_exists():
    """The blueprint's own input descriptions deep-link into
    docs/blueprint.md, and each test class names the section it covers.
    Nothing checks those, so renaming a heading silently breaks every
    link pointing at it - which is exactly what happened when the page
    was restructured: six anchors were left pointing at headings that no
    longer existed, in the file a user clicks through from the automation
    editor.

    Anchors are derived the way kramdown derives them (lowercase,
    non-alphanumerics to hyphens) rather than by building the site, so
    this runs in the unit layer with no Jekyll."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    page = (root / "docs" / "blueprint.md").read_text()

    def slug(heading: str) -> str:
        """kramdown's own rule: drop everything that isn't a word
        character, space or hyphen, then spaces become hyphens. Runs are
        NOT collapsed - "Brightness & Exclusions" really does become
        `brightness--exclusions`, and an apostrophe is removed rather
        than hyphenated."""
        return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", heading.lower()).strip())

    have = {slug(m) for m in re.findall(r"^#{2,3} (.+)$", page, re.MULTILINE)}

    referenced = set()
    for path in ("blueprints/automation/danspencer/flare.yaml", "tests/integration/test_blueprint.py"):
        for anchor in re.findall(r"blueprint(?:/|\.md)#([a-z0-9-]+)", (root / path).read_text()):
            referenced.add(anchor)

    assert referenced, "found no inbound links at all - has the link shape changed?"
    assert referenced <= have, f"dead anchors in docs/blueprint.md: {sorted(referenced - have)}"
