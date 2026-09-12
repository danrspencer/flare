"""The CI job summary is only useful if its arithmetic is right.

A miscount here is worse than no report at all: it would misreport the
very thing it exists to report on, and nobody double-checks a green
table. Same reasoning as tests/test_docs_site.py and
tests/test_static_imports.py - this repo tests its own tooling.

Pure layer: no Home Assistant, no pytest fixtures beyond tmp_path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "test_summary", REPO_ROOT / "scripts" / "test_summary.py"
)
assert _spec and _spec.loader
test_summary = importlib.util.module_from_spec(_spec)
# Registering before exec_module is required, not tidiness: @dataclass
# resolves sys.modules[cls.__module__].__dict__ while creating the
# class, which is None for a module that was never registered, and the
# whole file then fails to import with a bare AttributeError.
sys.modules[_spec.name] = test_summary
_spec.loader.exec_module(test_summary)


def write_xml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "junit.xml"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites name="pytest tests">'
        f'<testsuite name="pytest" tests="0" time="1.5">{body}</testsuite>'
        "</testsuites>"
    )
    return path


def test_it_splits_tests_into_the_three_layers(tmp_path):
    """The whole point of the report: which layer ran. The three fail
    for genuinely different reasons, so a single total hides the answer
    you actually want."""
    xml = write_xml(
        tmp_path,
        '<testcase classname="tests.behaviour.test_lighting" name="a" time="0.1" />'
        '<testcase classname="tests.integration.test_services" name="b" time="0.2" />'
        '<testcase classname="tests.test_curve" name="c" time="0.3" />',
    )
    layers, _ = test_summary.collect(xml)
    counts = {name: layer.total for name, layer in layers.items() if layer.total}

    assert counts == {
        "Behaviour — real blueprint + services, fake bulbs": 1,
        "Integration — real Home Assistant": 1,
        "Pure — no Home Assistant": 1,
    }


def test_integration_is_not_swallowed_by_the_catch_all(tmp_path):
    """LAYERS is matched by prefix with a "" catch-all last. If that
    entry were ever reordered ahead of the others, every test would
    report as Pure and the table would look plausible while being
    entirely wrong."""
    xml = write_xml(
        tmp_path,
        '<testcase classname="tests.integration.test_blueprint.TestX" name="a" time="0.1" />',
    )
    layers, _ = test_summary.collect(xml)

    assert layers["Integration — real Home Assistant"].total == 1
    assert layers["Pure — no Home Assistant"].total == 0


def test_a_teardown_error_is_not_counted_as_a_pass(tmp_path):
    """pytest itself reports such a test as BOTH passed and errored (its
    assertion ran and succeeded, then teardown blew up). The summary
    deliberately lets the error win: a test whose teardown exploded must
    not be advertised as green. This is the one place the report's
    arithmetic diverges from pytest's own, so it is pinned."""
    xml = write_xml(
        tmp_path,
        '<testcase classname="tests.test_x" name="a" time="0.1">'
        '<error message="RuntimeError: boom">trace</error>'
        "</testcase>",
    )
    layers, _ = test_summary.collect(xml)
    pure = layers["Pure — no Home Assistant"]

    assert (pure.total, pure.errored, pure.failed, pure.passed) == (1, 1, 0, 0)


def test_failures_errors_and_skips_are_counted_separately(tmp_path):
    xml = write_xml(
        tmp_path,
        '<testcase classname="tests.test_x" name="ok" time="0.1" />'
        '<testcase classname="tests.test_x" name="bad" time="0.1">'
        '<failure message="AssertionError">trace</failure></testcase>'
        '<testcase classname="tests.test_x" name="boom" time="0.1">'
        '<error message="RuntimeError">trace</error></testcase>'
        '<testcase classname="tests.test_x" name="skip" time="0.1">'
        '<skipped type="pytest.skip" message="why" /></testcase>',
    )
    layers, _ = test_summary.collect(xml)
    pure = layers["Pure — no Home Assistant"]

    assert (pure.total, pure.passed, pure.failed, pure.errored, pure.skipped) == (4, 1, 1, 1, 1)


def test_a_pipe_in_a_message_cannot_break_the_table(tmp_path):
    """Markdown tables are pipe-delimited, so an unescaped pipe in an
    assertion message silently splits the row into extra columns."""
    xml = write_xml(
        tmp_path,
        '<testcase classname="tests.test_x" name="bad" time="0.1">'
        '<failure message="got a | pipe">trace</failure></testcase>',
    )
    layers, wall = test_summary.collect(xml)
    rendered = test_summary.render(layers, wall)

    assert "\\|" in rendered
    assert "got a | pipe" not in rendered


def test_a_clean_run_reports_passed_not_a_failure_headline(tmp_path):
    xml = write_xml(
        tmp_path,
        '<testcase classname="tests.test_x" name="a" time="0.1" />'
        '<testcase classname="tests.test_x" name="b" time="0.1" />',
    )
    layers, wall = test_summary.collect(xml)
    rendered = test_summary.render(layers, wall)

    assert "✅ **2 passed**" in rendered
    assert "What went wrong" not in rendered


def test_empty_layers_are_left_out_of_the_table(tmp_path):
    """A house with no behaviour tests yet shouldn't get a row of
    zeroes - the table should say what ran, not what exists."""
    xml = write_xml(tmp_path, '<testcase classname="tests.test_x" name="a" time="0.1" />')
    layers, wall = test_summary.collect(xml)
    rendered = test_summary.render(layers, wall)

    assert "Pure — no Home Assistant" in rendered
    assert "Behaviour" not in rendered
