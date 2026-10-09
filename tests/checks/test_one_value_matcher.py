"""A light's reported values are read, converted and compared with a
target only in zone/matching.py, so override protection, grouping and
adoption can't disagree about what a light shows."""

import ast

from tests.support import COMPONENT as PACKAGE

HOME = PACKAGE / "zone" / "matching.py"
# The curve converts Kelvin for sending, never for comparing.
CONVERTS_FOR_SENDING = {PACKAGE / "schedule" / "curve.py"}
# What a light reports about its colour; reading any of these is matching.py's job.
LIGHT_COLOUR_ATTRIBUTES = {"color_temp_kelvin", "xy_color", "rgb_color", "hs_color"}


def _modules():
    for path in sorted(PACKAGE.rglob("*.py")):
        if path != HOME:
            yield path, ast.parse(path.read_text())


def test_only_matching_converts_colours():
    importers = [
        f"{path.relative_to(PACKAGE)}:{node.lineno}"
        for path, tree in _modules()
        if path not in CONVERTS_FOR_SENDING
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "homeassistant.util.color"
    ]
    assert importers == [], "compare a light's colour through zone/matching.py"


def test_only_matching_reads_a_lights_colour_from_its_state():
    """`<state>.attributes.get(...)` or `lookup.state_attr(e, ...)` for a colour."""
    readers = []
    for path, tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            args = [a.value for a in node.args if isinstance(a, ast.Constant)]
            on_attributes = node.func.attr == "get" and getattr(node.func.value, "attr", None) == "attributes"
            if (on_attributes or node.func.attr == "state_attr") and LIGHT_COLOUR_ATTRIBUTES & set(args):
                readers.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert readers == [], "read a light's colour through zone/matching.py"
