"""services.yaml, which HA shows in Developer Tools -> Actions.
compute_lighting_groups and apply_lighting each carry a full copy of their
shared fields (an anchor would leave a phantom top-level key), so the
copies are checked against each other."""

import yaml

from custom_components.flare.schedule.curve import DEFAULT_CURVE_VALUES
from tests.support import COMPONENT

SERVICES = yaml.safe_load((COMPONENT / "services.yaml").read_text())
PLANNER = SERVICES["compute_lighting_groups"]["fields"]
DISPATCHER = SERVICES["apply_lighting"]["fields"]

# Worded differently on purpose: one plans, the other writes.
INTENTIONALLY_DIFFERENT = {"prefer_rgb_color", "two_step_label", "zone_device_id"}


def test_every_documented_service_is_registered():
    """HA silently ignores a stray top-level key."""
    assert set(SERVICES) == {
        "compute_lighting_groups",
        "apply_lighting",
        "turn_off",
        "compute_curve",
        "compute_scene_coverage",
        "claims_check",
        "claims_record",
        "claims_clear",
        "export_schedule",
        "import_schedule",
    }


def test_apply_lighting_is_the_planner_plus_transition():
    assert set(DISPATCHER) - set(PLANNER) == {"transition"}
    assert set(PLANNER) <= set(DISPATCHER)


def test_shared_fields_have_not_drifted():
    drifted = [k for k in PLANNER if k not in INTENTIONALLY_DIFFERENT and PLANNER[k] != DISPATCHER[k]]
    assert drifted == [], "update both copies, or add to INTENTIONALLY_DIFFERENT"


def test_the_intentionally_different_fields_still_differ():
    for key in INTENTIONALLY_DIFFERENT:
        assert PLANNER[key] != DISPATCHER[key], f"{key} matches now; drop it from the allowlist"


def test_compute_curve_documents_the_real_defaults():
    fields = SERVICES["compute_curve"]["fields"]
    assert {k: fields[k].get("default") for k in DEFAULT_CURVE_VALUES} == DEFAULT_CURVE_VALUES
