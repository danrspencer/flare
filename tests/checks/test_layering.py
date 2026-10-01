"""The integration's packages import in one direction only:

    schedule/  -> const
    zone/  -> const
    services/  -> schedule/, zone/, const

and none reach back up into the package root. Parsed from the source."""

import ast

from tests.support import COMPONENT as PACKAGE

ALLOWED = {
    "schedule": {"schedule", "const"},
    "zone": {"zone", "const"},
    "services": {"services", "schedule", "zone", "const"},
}


def _area(module_parts: tuple) -> str:
    """A package name, or "__init__" for anything at the root."""
    return module_parts[0] if module_parts else "__init__"


def _imports(package: str):
    """Yield (file, imported area) for every relative import in `package`."""
    for path in sorted((PACKAGE / package).glob("*.py")):
        here = (package,)  # the package this file's `.` refers to, relative to the integration root
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom) or node.level == 0:
                continue
            base = here[: len(here) - (node.level - 1)]
            if node.module:
                yield path.name, _area(base + tuple(node.module.split(".")))
            else:  # `from .. import x` - each name is itself a module
                for alias in node.names:
                    yield path.name, _area(base + (alias.name,))


def test_no_package_imports_something_it_is_not_allowed_to():
    breaches = [
        f"{package}/{filename} imports {area}"
        for package, allowed in ALLOWED.items()
        for filename, area in _imports(package)
        if area not in allowed
    ]
    assert breaches == [], (
        "These break the dependency direction:\n  "
        + "\n  ".join(breaches)
    )


def test_the_check_actually_sees_imports():
    seen = {(package, area) for package in ALLOWED for _, area in _imports(package)}
    assert ("services", "schedule") in seen, "services/ should be importing from schedule/"
    assert ("services", "zone") in seen, "services/ should be importing from zone/"
    assert ("schedule", "const") in seen and ("zone", "const") in seen


def test_every_package_is_covered():
    packages = {p.name for p in PACKAGE.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    assert packages == set(ALLOWED), f"add a rule for: {sorted(packages - set(ALLOWED))}"
