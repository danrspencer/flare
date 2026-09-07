"""
The www/ modules must import each other RELATIVELY.

That is the assumption the versioned static URL rests on. The files are
served from `/flare_static/<version>/`, and a relative import resolves
against the importing module's own URL - so `./flare-curve-card.js` from
`/flare_static/1.2.3/flare-view-strategy.js` lands on
`/flare_static/1.2.3/flare-curve-card.js`, the same URL the frontend was
told to load, and the module is evaluated once.

Rewrite one as an absolute path and that file is fetched again under a
second URL, whereupon the second `customElements.define` for the same tag
throws. (It is also why the version is a path segment and not a `?v=`
query: a query is not inherited by a relative import.)
"""

import re
from pathlib import Path

import pytest

WWW = Path(__file__).resolve().parent.parent / "custom_components" / "flare" / "www"
JS_FILES = sorted(WWW.glob("*.js"))

# Static `import ... from '<specifier>'` / `import '<specifier>'` only -
# a dynamic import() is resolved at call time and is not what the
# double-evaluation hazard is about.
IMPORT_RE = re.compile(r"""^\s*import\b[^'"\n]*['"]([^'"]+)['"]""", re.MULTILINE)


def test_there_are_js_files_to_check():
    """Without this, the parametrised tests below silently pass on an
    empty glob if the directory ever moves."""
    assert JS_FILES, f"no .js files found under {WWW}"


@pytest.mark.parametrize("js", JS_FILES, ids=lambda p: p.name)
def test_imports_are_relative_and_point_at_files_that_exist(js):
    for specifier in IMPORT_RE.findall(js.read_text()):
        assert specifier.startswith("./"), (
            f"{js.name} imports {specifier!r}; it must be relative so it inherits the "
            "version from the importing module's URL"
        )
        assert (WWW / specifier[2:]).is_file(), f"{js.name} imports missing {specifier}"
