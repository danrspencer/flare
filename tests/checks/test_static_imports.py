"""The www/ modules import each other relatively, so an import inherits
the versioned static path (`/flare_static/<version>/`) of the module doing
the importing. An absolute import would load a module a second time under
another URL, and its customElements.define would throw."""

import re

import pytest

from tests.support import WWW

JS_FILES = sorted(WWW.glob("*.js"))

# Static imports only.
IMPORT_RE = re.compile(r"""^\s*import\b[^'"\n]*['"]([^'"]+)['"]""", re.MULTILINE)


def test_there_are_js_files_to_check():
    assert JS_FILES, f"no .js files found under {WWW}"


@pytest.mark.parametrize("js", JS_FILES, ids=lambda p: p.name)
def test_imports_are_relative_and_point_at_files_that_exist(js):
    for specifier in IMPORT_RE.findall(js.read_text()):
        assert specifier.startswith("./"), (
            f"{js.name} imports {specifier!r}; it must be relative so it inherits the "
            "version from the importing module's URL"
        )
        assert (WWW / specifier[2:]).is_file(), f"{js.name} imports missing {specifier}"
