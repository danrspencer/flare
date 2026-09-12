"""The trace view must not misreport which step failed.

Worse than no trace at all: a renderer that shows a failing condition as
passing sends you down the wrong path with confidence. Same reasoning as
tests/test_test_summary.py.

Pure layer: no Home Assistant, no fixtures beyond tmp_path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "trace_summary", REPO_ROOT / "scripts" / "trace_summary.py"
)
assert _spec and _spec.loader
trace_summary = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = trace_summary
_spec.loader.exec_module(trace_summary)


def write_dump(tmp_path: Path, *, outcome: str = "passed", steps: dict | None = None) -> Path:
    payload = {
        "test": "tests/behaviour/test_lighting.py::test_it_does_the_thing",
        "outcome": outcome,
        "traces": [
            {
                "trigger": "state of binary_sensor.hall_occupancy",
                "script_execution": "finished",
                "last_step": "action/0",
                "trace": steps if steps is not None else {},
            }
        ],
    }
    path = tmp_path / "dump.json"
    path.write_text(json.dumps(payload))
    return path


def test_a_failed_condition_is_marked_as_failed(tmp_path):
    """The single most important thing this renders. HA records a
    condition's outcome as {"result": {"result": false}}; showing that
    as anything but a cross defeats the point of the trace."""
    dump = write_dump(
        tmp_path,
        steps={"condition/0": [{"path": "condition/0", "result": {"result": False}}]},
    )
    _, block = trace_summary.render_dump(dump)

    assert "✗ condition/0" in "\n".join(block)


def test_a_passed_condition_is_marked_as_passed(tmp_path):
    dump = write_dump(
        tmp_path,
        steps={"condition/0": [{"path": "condition/0", "result": {"result": True}}]},
    )
    _, block = trace_summary.render_dump(dump)

    assert "✓ condition/0" in "\n".join(block)


def test_a_step_with_no_recorded_result_is_not_claimed_to_have_passed(tmp_path):
    """Plenty of steps record no result at all. Defaulting those to a
    tick would invent information the trace never contained."""
    dump = write_dump(tmp_path, steps={"action/0": [{"path": "action/0"}]})
    _, block = trace_summary.render_dump(dump)
    text = "\n".join(block)

    assert "· action/0" in text
    assert "✓ action/0" not in text


def test_interesting_variables_are_surfaced_next_to_their_step(tmp_path):
    """A trace carries every variable at every step - far more than
    anyone reads. The blueprint's decision rests on a known handful."""
    dump = write_dump(
        tmp_path,
        steps={
            "action/0": [
                {
                    "path": "action/0",
                    "changed_variables": {
                        "allow_turn_on": True,
                        "something_noisy": "x" * 500,
                    },
                }
            ]
        },
    )
    _, block = trace_summary.render_dump(dump)
    text = "\n".join(block)

    assert "allow_turn_on = true" in text
    assert "something_noisy" not in text


def test_a_failing_test_expands_and_a_passing_one_collapses(tmp_path):
    """A failure is the one you want open on arrival; a pass shouldn't
    push the results table off the page."""
    failed_dump = write_dump(tmp_path, outcome="failed")
    failed, block = trace_summary.render_dump(failed_dump)

    assert failed
    assert "<details open>" in block[0]

    other = tmp_path / "other.json"
    other.write_text(json.dumps({"test": "t", "outcome": "passed", "traces": []}))
    passed, block2 = trace_summary.render_dump(other)

    assert not passed
    assert block2[0] == "<details>"


def test_nesting_follows_the_step_path_depth(tmp_path):
    """HA's paths encode structure; flattening them loses which branch a
    step belongs to."""
    dump = write_dump(
        tmp_path,
        steps={
            "action/0": [{"path": "action/0"}],
            "action/0/default/1/then/0": [{"path": "action/0/default/1/then/0"}],
        },
    )
    _, block = trace_summary.render_dump(dump)
    lines = [line for line in "\n".join(block).splitlines() if "action/0" in line]

    shallow = next(line for line in lines if line.strip().endswith("action/0"))
    deep = next(line for line in lines if "then/0" in line)
    assert len(deep) - len(deep.lstrip()) > len(shallow) - len(shallow.lstrip())


def step_lines(block: list[str]) -> list[str]:
    """Just the step paths from the rendered tree, in order.

    Searching the whole rendered text is a trap: the header carries
    `last step: action/0`, so a bare `text.index("action/0")` finds the
    HEADER rather than the tree and the assertion silently measures the
    wrong thing. Caught exactly that way - the first version of the
    ordering test failed against its own header.
    """
    inside = False
    paths = []
    for line in "\n".join(block).splitlines():
        if line.strip() == "```":
            inside = not inside
            continue
        if inside and (stripped := line.strip()):
            marker, _, rest = stripped.partition(" ")
            if marker in {"✓", "✗", "·"}:
                paths.append(rest)
    return paths


def test_steps_render_in_execution_order_not_alphabetical(tmp_path):
    """Sorting paths as strings puts `trigger/3` below `action/0` and
    renders the run backwards, burying the trigger's variables - which
    are the first thing anyone reads - at the very bottom. Caught on a
    real captured trace, not in a fixture."""
    dump = write_dump(
        tmp_path,
        steps={
            "action/0": [{"path": "action/0"}],
            "condition/0": [{"path": "condition/0", "result": {"result": True}}],
            "trigger/3": [{"path": "trigger/3"}],
        },
    )
    _, block = trace_summary.render_dump(dump)

    assert step_lines(block) == ["trigger/3", "condition/0", "action/0"]


def test_numeric_path_segments_sort_as_numbers(tmp_path):
    """`step/10` must not sort before `step/2`."""
    dump = write_dump(
        tmp_path,
        steps={
            "action/2": [{"path": "action/2"}],
            "action/10": [{"path": "action/10"}],
        },
    )
    _, block = trace_summary.render_dump(dump)

    assert step_lines(block) == ["action/2", "action/10"]


def test_a_pipe_in_a_value_cannot_break_rendering(tmp_path):
    dump = write_dump(
        tmp_path,
        steps={
            "action/0": [
                {"path": "action/0", "changed_variables": {"allow_turn_on": "a | b"}}
            ]
        },
    )
    _, block = trace_summary.render_dump(dump)

    assert "\\|" in "\n".join(block)


def test_no_dumps_renders_nothing_at_all(tmp_path, capsys):
    """A run with no behaviour tests should not print an empty section
    header into the job summary."""
    assert trace_summary.main(["trace_summary.py", str(tmp_path)]) == 0

    assert capsys.readouterr().out == ""
