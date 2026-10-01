"""The trace capture must capture something: if it stops, every other
test still passes. Self-contained rather than reading what other tests
left in TRACE_DIR, which would fail in isolation."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant

from tests.functional.behaviour.harness import HALL_SENSOR, dump_traces, occupancy

HALL = HALL_SENSOR


async def test_a_blueprint_run_produces_a_complete_trace(
    hass: HomeAssistant, zone, add_bulbs, setup_room
) -> None:
    """And finished: a trace read mid-run shows unreached branches."""
    from homeassistant.components.trace.const import DATA_TRACE

    (bulb,) = await add_bulbs("hall")
    occupancy(hass, HALL, "off")
    await setup_room(lights=[bulb], occupancy_sensors=[HALL])
    occupancy(hass, HALL, "on")
    await hass.async_block_till_done()

    traces = [
        trace
        for bucket in (hass.data.get(DATA_TRACE) or {}).values()
        for trace in bucket.all_traces()
    ]
    assert traces, "the blueprint run produced no trace at all"

    captured = traces[0].as_extended_dict()
    assert captured["trace"], "the trace recorded no steps"
    assert captured.get("blueprint_inputs"), (
        "blueprint_inputs is empty - the trace cannot be tied back to the "
        "blueprint that produced it"
    )
    assert captured["state"] == "stopped", f"captured mid-run: {captured['state']}"
    assert captured["script_execution"] == "finished"


async def test_the_capture_writes_a_readable_dump(
    hass: HomeAssistant, zone, add_bulbs, setup_room, tmp_path
) -> None:
    """The write half, exercised against a temp directory.

    capture_trace writes at fixture teardown, so a test can never see
    its own file. Calling the same helper directly is what makes this
    testable at all without depending on another test having run.
    """
    (bulb,) = await add_bulbs("hall")
    occupancy(hass, HALL, "off")
    await setup_room(lights=[bulb], occupancy_sensors=[HALL])
    occupancy(hass, HALL, "on")
    await hass.async_block_till_done()

    written = dump_traces(hass, tmp_path, test_id="probe::a_test", outcome="failed")

    assert written is not None, "nothing was written despite a real blueprint run"
    payload = json.loads(written.read_text())

    assert payload["test"] == "probe::a_test"
    assert payload["outcome"] == "failed"
    assert payload["traces"], "the dump holds no traces"
    assert payload["traces"][0]["trace"], "the dumped trace recorded no steps"
