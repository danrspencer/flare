"""The input a flare reads from a room automation is one the blueprint
declares, of the kind the flare expects."""

from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA

from custom_components.flare.const import BLUEPRINT_LIGHTS_INPUT
from custom_components.flare.flares.automation import TARGET, lights_input_kinds
from tests.support import load_blueprint


def _blueprint() -> Blueprint:
    return Blueprint(load_blueprint(), expected_domain="automation", schema=BLUEPRINT_SCHEMA)


def test_the_lights_input_is_a_target():
    assert lights_input_kinds(_blueprint())[BLUEPRINT_LIGHTS_INPUT] == TARGET

