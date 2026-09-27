"""scripts/test_summary.py, which turns junit.xml into CI's job summary."""

from pathlib import Path

import pytest

from tests.support import load_script

test_summary = load_script("test_summary")
UNIT = "Unit — no running Home Assistant"


def collect(tmp_path: Path, body: str):
    path = tmp_path / "junit.xml"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
        f'<testsuite name="pytest" tests="0" time="1.5">{body}</testsuite></testsuites>'
    )
    return test_summary.collect(path)


def case(classname="tests.unit.component.test_x", name="a", child=""):
    return f'<testcase classname="{classname}" name="{name}" time="0.1">{child}</testcase>'


@pytest.mark.parametrize(
    ("classname", "layer"),
    [
        ("tests.unit.component.test_curve", UNIT),
        ("tests.unit.dashboard.test_js_parity", UNIT),
        ("tests.checks.test_layering", "Checks — the repository itself"),
        ("tests.functional.component.test_services", "Functional — real Home Assistant"),
        ("tests.functional.blueprint.test_blueprint.TestX", "Functional — real Home Assistant"),
        ("tests.functional.behaviour.test_lighting", "Behaviour — real blueprint + services, fake bulbs"),
        ("", "Other"),
    ],
)
def test_each_test_is_counted_in_its_layer(tmp_path, classname, layer):
    layers, _ = collect(tmp_path, case(classname))
    assert {name for name, l in layers.items() if l.total} == {layer}


def test_failures_errors_and_skips_are_counted_separately(tmp_path):
    layers, _ = collect(
        tmp_path,
        case(name="ok")
        + case(name="bad", child='<failure message="AssertionError">t</failure>')
        + case(name="boom", child='<error message="RuntimeError">t</error>')
        + case(name="skip", child='<skipped type="pytest.skip" message="why" />'),
    )
    unit = layers[UNIT]
    assert (unit.total, unit.passed, unit.failed, unit.errored, unit.skipped) == (4, 1, 1, 1, 1)


def test_a_teardown_error_is_not_counted_as_a_pass(tmp_path):
    """pytest reports it as both passed and errored; the error wins."""
    layers, _ = collect(tmp_path, case(child='<error message="RuntimeError: boom">t</error>'))
    unit = layers[UNIT]
    assert (unit.total, unit.errored, unit.passed) == (1, 1, 0)


def test_a_pipe_in_a_message_cannot_break_the_table(tmp_path):
    rendered = test_summary.render(*collect(tmp_path, case(child='<failure message="got a | pipe">t</failure>')))
    assert "got a \\| pipe" in rendered


def test_a_clean_run_reports_passed(tmp_path):
    rendered = test_summary.render(*collect(tmp_path, case(name="a") + case(name="b")))
    assert "✅ **2 passed**" in rendered
    assert "What went wrong" not in rendered


def test_empty_layers_are_left_out(tmp_path):
    rendered = test_summary.render(*collect(tmp_path, case()))
    assert UNIT in rendered
    assert "Behaviour" not in rendered


def test_a_missing_report_says_so(tmp_path, capsys):
    assert test_summary.main(["test_summary.py", str(tmp_path / "missing.xml")]) == 0
    assert "produced no report" in capsys.readouterr().out
