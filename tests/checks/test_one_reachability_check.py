"""Whether HA can reach an entity is decided by const.is_reachable() alone:
nothing else compares a state with "unavailable" or "unknown"."""

import ast

from tests.support import COMPONENT as PACKAGE

UNREACHABLE = {"unavailable", "unknown"}


def _compares_a_state_with_unreachable(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "is_state":
        return any(isinstance(a, ast.Constant) and a.value in UNREACHABLE for a in node.args)
    if not isinstance(node, ast.Compare):
        return False
    sides = [node.left, *node.comparators]
    reads_state = any(isinstance(side, ast.Attribute) and side.attr == "state" for side in sides)
    constants = {
        c.value
        for side in sides
        for c in ([side] if isinstance(side, ast.Constant) else getattr(side, "elts", []))
        if isinstance(c, ast.Constant)
    }
    return reads_state and bool(constants & UNREACHABLE)


def test_only_const_decides_reachability():
    offenders = [
        f"{path.relative_to(PACKAGE)}:{node.lineno}"
        for path in sorted(PACKAGE.rglob("*.py"))
        if path.name != "const.py"
        for node in ast.walk(ast.parse(path.read_text()))
        if _compares_a_state_with_unreachable(node)
    ]
    assert offenders == [], "use const.is_reachable()"


def test_the_check_sees_a_comparison():
    tree = ast.parse('state.state in ("unavailable", "unknown")\nnew.state == "unknown"\nlookup.is_state(e, "unavailable")')
    assert sum(_compares_a_state_with_unreachable(n) for n in ast.walk(tree)) == 3
