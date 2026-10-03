"""Every consumer of override protection reads a light through
classify_state(), so none can feed classify() its own idea of live state."""

import ast

from tests.support import COMPONENT as PACKAGE

HOME = PACKAGE / "zone" / "override_protection.py"


def test_only_override_protection_calls_classify_directly():
    callers = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path == HOME:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "classify":
                callers.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert callers == [], "call classify_state() instead"
