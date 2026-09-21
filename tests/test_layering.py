"""
The integration's code is grouped by concept, and the point of that is the
direction the imports run.

The schedule (what lights should look like) and the claims (who owns a light)
are each exposed through both entities and services, so neither can live with
either. They are their own packages instead, and depend on nothing:

    schedule/  -> const only
    tracking/  -> const only
    services/  -> schedule/, tracking/, const

The entity platforms, config flow and setup at the package root may use
anything. What none of the three packages may do is reach back up into the
root (a platform, the config flow, __init__), or sideways into each other
where the list above doesn't allow it - that is how the two-way tangle
between entities and services this layout replaced would creep back.

Parsed from the source, so it needs no Home Assistant and cannot be fooled by
an import that only runs on some code path.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "custom_components" / "flare"

ALLOWED = {
    "schedule": {"schedule", "const"},
    "tracking": {"tracking", "const"},
    "services": {"services", "schedule", "tracking", "const"},
}


def _area(module_parts: tuple) -> str:
    """Which part of the integration a module path (relative to
    custom_components/flare) belongs to: a package name, or the root
    module's own name for anything sitting at the top level."""
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
        "These break the dependency direction described in this module's docstring:\n  "
        + "\n  ".join(breaches)
    )


def test_the_check_actually_sees_imports():
    """Guards against the test passing because the parser found nothing."""
    seen = {(package, area) for package in ALLOWED for _, area in _imports(package)}
    assert ("services", "schedule") in seen, "services/ should be importing from schedule/"
    assert ("services", "tracking") in seen, "services/ should be importing from tracking/"
    assert ("schedule", "const") in seen and ("tracking", "const") in seen


def test_every_package_is_covered():
    """A fourth package added without a rule would be exempt from all of this."""
    packages = {p.name for p in PACKAGE.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    assert packages == set(ALLOWED), f"add a rule for: {sorted(packages - set(ALLOWED))}"
