"""services.yaml, which HA shows in Developer Tools -> Actions."""

import yaml

from custom_components.flare.schedule.curve import DEFAULT_CURVE_VALUES
from tests.support import COMPONENT

SERVICES = yaml.safe_load((COMPONENT / "services.yaml").read_text())


def test_compute_curve_documents_the_real_defaults():
    fields = SERVICES["compute_curve"]["fields"]
    assert {k: fields[k].get("default") for k in DEFAULT_CURVE_VALUES} == DEFAULT_CURVE_VALUES
