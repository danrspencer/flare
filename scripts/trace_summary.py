"""Render a captured automation trace as a readable tree.

tests/behaviour/ captures the blueprint's real Home Assistant automation
trace (see its conftest.py). This turns one of those dumps into the view
you actually want when a blueprint run did the wrong thing: which
conditions passed or failed, which `choose:` branch ran, and what the
decisive variables resolved to.

It is NOT Home Assistant's trace viewer and cannot become it - the
websocket API is read-only and HA never reads its trace store back at
startup, so a trace produced here can't be loaded into a live instance.
This is the same information, rendered ourselves.

A trace is ~28 steps with full `changed_variables` at each one, which is
far more than anyone reads. The signal is the conditions and their
results, plus the branch taken, so that is what the tree leads with.

Usage:  python scripts/trace_summary.py trace-dumps/*.json
        python scripts/trace_summary.py trace-dumps/ >> "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Variables worth surfacing next to a step. The blueprint's whole
# decision rests on these, and they are the first thing looked at when
# diagnosing a run - see CLAUDE.md's blueprint section.
INTERESTING = (
    "allow_turn_on",
    "occupied",
    "room_is_idle",
    "idle_entities",
    "resolved_entities",
    "brightness_multipliers",
    "adaptive_target_entities",
    "entities_still_on",
    "occupancy_clear_for_wait",
    "script_transition",
)

# Rendering every trace expanded would blow GitHub's 1 MiB job summary
# cap once there are more than a handful of behaviour tests, and bury
# the results table above it. Failures expand; passes stay collapsed.
MAX_EXPANDED = 3


def result_of(entries: list[dict[str, Any]]) -> Any:
    """The result a step recorded, if it recorded one."""
    for entry in entries:
        result = entry.get("result")
        if isinstance(result, dict) and "result" in result:
            return result["result"]
    return None


def variables_at(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The interesting subset of what changed at this step."""
    found: dict[str, Any] = {}
    for entry in entries:
        for name, value in (entry.get("changed_variables") or {}).items():
            if name in INTERESTING:
                found[name] = value
    return found


def brief(value: Any, limit: int = 90) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text.replace("|", "\\|")


def execution_order(path: str) -> tuple[int, list[Any]]:
    """Sort key putting steps in the order they actually ran.

    Sorting paths as plain strings puts `trigger/3` AFTER `action/0` and
    `condition/0`, rendering the run backwards - and burying the trigger's
    variables, which are the first thing anyone reads, at the bottom.
    HA runs trigger, then condition, then action, so rank on that first.

    Within a path, numeric segments must compare as numbers or `step/10`
    sorts before `step/2`.
    """
    top = path.split("/", 1)[0]
    rank = {"trigger": 0, "condition": 1, "action": 2}.get(top, 3)
    segments: list[Any] = [
        int(segment) if segment.isdigit() else segment for segment in path.split("/")
    ]
    return rank, segments


def render_trace(trace: dict[str, Any]) -> list[str]:
    steps: dict[str, list[dict[str, Any]]] = trace.get("trace", {})
    lines: list[str] = []

    lines.append(f"- **trigger**: {trace.get('trigger', '?')}")
    lines.append(f"- **finished as**: {trace.get('script_execution', '?')}")
    lines.append(f"- **last step**: `{trace.get('last_step', '?')}`")
    lines.append("")
    lines.append("```")

    for path in sorted(steps, key=execution_order):
        entries = steps[path]
        depth = path.count("/")
        indent = "  " * depth
        outcome = result_of(entries)

        if outcome is True:
            marker = "✓"
        elif outcome is False:
            marker = "✗"
        else:
            marker = "·"

        lines.append(f"{indent}{marker} {path}")

        for name, value in variables_at(entries).items():
            lines.append(f"{indent}    {name} = {brief(value)}")

    lines.append("```")
    return lines


def render_dump(path: Path) -> tuple[bool, list[str]]:
    payload = json.loads(path.read_text())
    failed = payload.get("outcome") == "failed"
    name = payload.get("test", path.stem)

    body: list[str] = []
    for trace in payload.get("traces", []):
        body += render_trace(trace)
        body.append("")

    icon = "❌" if failed else "✅"
    summary = f"{icon} <code>{name}</code>"
    return failed, [f"<details{' open' if failed else ''}>", f"<summary>{summary}</summary>", "", *body, "</details>", ""]


def collect_dumps(args: list[str]) -> list[Path]:
    paths: list[Path] = []
    for arg in args:
        candidate = Path(arg)
        if candidate.is_dir():
            paths += sorted(candidate.glob("*.json"))
        elif candidate.exists():
            paths.append(candidate)
    return paths


def main(argv: list[str]) -> int:
    dumps = collect_dumps(argv[1:])
    if not dumps:
        # Not an error: a run with no behaviour tests captures nothing,
        # and the summary should simply not carry a trace section.
        return 0

    rendered: list[tuple[bool, list[str]]] = [render_dump(path) for path in dumps]
    failures = sum(1 for failed, _ in rendered if failed)

    print("## Blueprint traces")
    print()
    print(
        f"{len(dumps)} automation trace(s) captured"
        + (f", {failures} from failing tests" if failures else "")
        + ". `✓`/`✗` are the results Home Assistant recorded for each step."
    )
    print()

    expanded = 0
    for failed, block in rendered:
        if not failed:
            expanded += 1
            if expanded > MAX_EXPANDED:
                continue
        print("\n".join(block))

    if expanded > MAX_EXPANDED:
        print(
            f"_{expanded - MAX_EXPANDED} passing trace(s) omitted for brevity — "
            "all are in the `blueprint-traces` artifact._"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
