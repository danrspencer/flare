"""A light's reported values are read, converted and compared with a
target only in tracking/matching.py, so override protection, grouping and
adoption can't disagree about what a light shows."""

import ast

from tests.support import COMPONENT as PACKAGE

HOME = PACKAGE / "tracking" / "matching.py"
# The curve converts Kelvin for sending, never for comparing.
CONVERTS_FOR_SENDING = {PACKAGE / "schedule" / "curve.py"}
# What a light reports about its colour, as strings or HA's ATTR_ names;
# reading any of these is matching.py's job.
LIGHT_COLOUR_ATTRIBUTES = {"color_temp_kelvin", "xy_color", "rgb_color", "hs_color"}
LIGHT_COLOUR_ATTRIBUTE_NAMES = {f"ATTR_{attribute.upper()}" for attribute in LIGHT_COLOUR_ATTRIBUTES}


def _names_a_colour(arg: ast.expr) -> bool:
    if isinstance(arg, ast.Constant):
        return arg.value in LIGHT_COLOUR_ATTRIBUTES
    name = arg.id if isinstance(arg, ast.Name) else arg.attr if isinstance(arg, ast.Attribute) else None
    return name in LIGHT_COLOUR_ATTRIBUTE_NAMES


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
    assert importers == [], "compare a light's colour through tracking/matching.py"


def test_only_matching_reads_a_lights_colour_from_its_state():
    """`<state>.attributes.get(...)` or `lookup.state_attr(e, ...)` for a colour."""
    readers = []
    for path, tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            on_attributes = node.func.attr == "get" and getattr(node.func.value, "attr", None) == "attributes"
            if (on_attributes or node.func.attr == "state_attr") and any(_names_a_colour(a) for a in node.args):
                readers.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert readers == [], "read a light's colour through tracking/matching.py"
