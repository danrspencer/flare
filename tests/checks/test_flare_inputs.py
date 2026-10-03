"""The inputs a flare reads from a room automation are ones the blueprint
declares, and of the kinds the flare expects."""

from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA

from custom_components.flare.const import BLUEPRINT_LIGHTS_INPUT, BLUEPRINT_ZONE_INPUT
from custom_components.flare.flares.automation import TARGET, lights_input_kinds, zone_inputs
from tests.support import load_blueprint


def _blueprint() -> Blueprint:
    return Blueprint(load_blueprint(), expected_domain="automation", schema=BLUEPRINT_SCHEMA)


def test_the_lights_input_is_a_target():
    assert lights_input_kinds(_blueprint())[BLUEPRINT_LIGHTS_INPUT] == TARGET


def test_the_zone_input_is_the_only_zone_picker():
    assert zone_inputs(_blueprint()) == [BLUEPRINT_ZONE_INPUT]
