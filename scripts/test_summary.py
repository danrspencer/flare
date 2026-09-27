"""Turn pytest's JUnit XML into a GitHub Actions job summary.

Written to $GITHUB_STEP_SUMMARY, so it renders as a table on the run
page, with no third-party action or extra permissions.

The point is "what ran", by layer (see CONTRIBUTING.md's Testing):

  Unit        no running Home Assistant
  Checks      consistency of the repository itself
  Functional  a real Home Assistant instance
  Behaviour   functional, end to end: real blueprint + services, fake bulbs

Usage:  python scripts/test_summary.py junit.xml >> "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# First matching prefix wins, so behaviour comes before functional.
LAYERS: dict[str, str] = {
    "tests.unit": "Unit — no running Home Assistant",
    "tests.checks": "Checks — the repository itself",
    "tests.functional.behaviour": "Behaviour — real blueprint + services, fake bulbs",
    "tests.functional": "Functional — real Home Assistant",
    "": "Other",
}


@dataclass
class Layer:
    name: str
    total: int = 0
    failed: int = 0
    skipped: int = 0
    errored: int = 0
    seconds: float = 0.0
    problems: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return self.total - self.failed - self.skipped - self.errored


def layer_for(classname: str) -> str:
    for prefix, label in LAYERS.items():
        if classname.startswith(prefix):
            return label
    return LAYERS[""]


def collect(xml_path: Path) -> tuple[dict[str, Layer], float]:
    root = ET.parse(xml_path).getroot()
    layers = {label: Layer(label) for label in LAYERS.values()}
    wall = 0.0

    for suite in root.iter("testsuite"):
        wall += float(suite.get("time", 0.0))

    for case in root.iter("testcase"):
        classname = case.get("classname", "")
        layer = layers[layer_for(classname)]
        layer.total += 1
        layer.seconds += float(case.get("time", 0.0))

        # A test can carry a failure AND an error (an assertion that
        # passed, then a teardown that blew up) - count the error, since
        # it is the louder of the two and the one most likely to be
        # missed. Errors are a separate element from failures precisely
        # because they mean something different: not "the assertion was
        # wrong" but "this never got to have an opinion".
        # A collection error has no classname at all, so joining
        # unconditionally renders it with a leading dot.
        case_name = case.get("name", "?")
        name = f"{classname}.{case_name}" if classname else case_name
        if (error := case.find("error")) is not None:
            layer.errored += 1
            layer.problems.append(("error", name, error.get("message", "")))
        elif (failure := case.find("failure")) is not None:
            layer.failed += 1
            layer.problems.append(("failed", name, failure.get("message", "")))
        elif case.find("skipped") is not None:
            layer.skipped += 1

    return layers, wall


def first_line(message: str, limit: int = 160) -> str:
    line = (message or "").strip().splitlines()
    text = line[0] if line else "(no message)"
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    # Pipes would break out of the markdown table cell.
    return text.replace("|", "\\|")


def render(layers: dict[str, Layer], wall: float) -> str:
    used = [layer for layer in layers.values() if layer.total]
    total = sum(layer.total for layer in used)
    failed = sum(layer.failed for layer in used)
    skipped = sum(layer.skipped for layer in used)
    errored = sum(layer.errored for layer in used)
    passed = total - failed - skipped - errored

    if failed or errored:
        headline = f"❌ **{failed + errored} of {total} did not pass**"
    else:
        headline = f"✅ **{passed} passed**"

    parts = [
        "## Test results",
        "",
        f"{headline} — {total} tests in {wall:.1f}s",
        "",
        "| Layer | Tests | Passed | Failed | Errors | Skipped | Time |",
        "| --- | --: | --: | --: | --: | --: | --: |",
    ]
    for layer in used:
        parts.append(
            f"| {layer.name} | {layer.total} | {layer.passed} | {layer.failed} "
            f"| {layer.errored} | {layer.skipped} | {layer.seconds:.1f}s |"
        )

    problems = [(kind, name, msg) for layer in used for kind, name, msg in layer.problems]
    if problems:
        parts += ["", "### What went wrong", "", "| | Test | Message |", "| --- | --- | --- |"]
        for kind, name, message in problems:
            icon = "💥" if kind == "error" else "❌"
            parts.append(f"| {icon} | `{name}` | {first_line(message)} |")

    parts.append("")
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    xml_path = Path(argv[1])
    if not xml_path.exists():
        # pytest can die before writing anything (a collection error, an
        # import that raises at module scope). Say so in the summary
        # rather than failing the step and leaving the run page blank.
        print("## Test results\n\n⚠️ pytest produced no report — it likely failed before collection.\n")
        return 0

    layers, wall = collect(xml_path)
    print(render(layers, wall))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
