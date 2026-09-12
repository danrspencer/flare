"""The trace capture must actually capture something.

Mutation testing found this gap rather than reasoning about it: with the
capture fixture disabled outright, all 529 tests still passed and zero
trace files were written. The renderer (tests/test_trace_summary.py) is
well covered, but nothing noticed that the thing feeding it had stopped.

That matters more than it looks. The capture exists to explain a
FAILING run, so a silent breakage surfaces at exactly the moment it is
needed and not one moment earlier - and a green build looks identical
either way. See tests/behaviour/conftest.py's capture_trace.

Deliberately self-contained. An earlier version asserted on whatever
sibling tests had left in TRACE_DIR, which passed in a full run and
FAILED in isolation - an order-dependent test that reports "the capture
is broken" when the capture is fine is the same misleading-signal
problem it was added to prevent.
"""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant

from tests.behaviour.conftest import dump_traces, occupancy

HALL = "binary_sensor.hall_occupancy"


async def test_a_blueprint_run_produces_a_complete_trace(
    hass: HomeAssistant, flare, add_bulbs, setup_room
) -> None:
    """The data the capture depends on is there, and it is finished.

    A trace read mid-run is truncated and actively misleading: it shows
    a branch as never reached when it simply had not run yet.
    """
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
    hass: HomeAssistant, flare, add_bulbs, setup_room, tmp_path
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
