from enum import StrEnum

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

DOMAIN = "flare"

# What HA reports for an entity it can't reach, or hasn't heard from yet.
UNREACHABLE_STATES = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})


def is_reachable(state: State | None) -> bool:
    """Whether HA has a real state for an entity: it exists, and isn't
    unavailable or unknown. Every check of reachability goes through this."""
    return state is not None and state.state not in UNREACHABLE_STATES


class Phase(StrEnum):
    """The schedule's phases, in the order a day runs through them. Their
    names are the schedule sensor's states."""

    MORNING = "Morning"
    DAY = "Day"
    EVENING = "Evening"
    NIGHT = "Night"


PHASES = [phase.value for phase in Phase]
# The phase override's "no override".
PHASE_AUTO = "Auto"
PHASE_OPTIONS = [PHASE_AUTO, *PHASES]

# Subentry type for a schedule sensor.
SUBENTRY_TYPE_SENSOR = "sensor"

# Options key: bulb models needing two-step transitions (see two_step.py).
CONF_TWO_STEP_MODELS = "two_step_models"

# Subentry type for a zone, before 2.0. Only the migration that removes
# them reads it.
SUBENTRY_TYPE_ZONE = "state"

# Fired when a tracked light becomes "overridden", with both claims and
# the live values at that moment (see sensor.py's _refresh_statuses).
EVENT_LIGHT_OVERRIDDEN = "flare_light_overridden"
EVENT_LIGHTS_CONTROLLED = "flare_lights_controlled"
EVENT_LIGHTS_RELEASED = "flare_lights_released"

# One config entry per kind of thing, because HA's integration page can't
# group subentries by type. The values are stored in each entry's data.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_SCHEDULES = "schedules"
ENTRY_TYPE_SETTINGS = "tracking"
ENTRY_TYPE_FLARES = "flares"

# Subentry type for a flare: a light that runs an automation.
SUBENTRY_TYPE_FLARE = "flare"

# A flare's subentry data.
CONF_AUTOMATION = "automation"  # entity registry id, which survives renames
CONF_LIGHTS_INPUT = "lights_input"  # the blueprint input holding the lights
CONF_LIGHTS_INPUT_KIND = "lights_input_kind"  # "target", or the target key its value is
CONF_LIGHTS_TARGET = "lights_target"  # a plain automation's lights, as a target
CONF_AREA = "area_id"  # where the flare's device starts out

# Our blueprint's input naming the room's lights.
BLUEPRINT_LIGHTS_INPUT = "room_target"

# Options keys: how close a light must be to its target, as a percentage of
# the target brightness and in mireds of colour temperature, to be left alone:
# not sent anything, and still FLARE's when it reports back. About one
# just-noticeable difference, so only a change someone would see is an
# override.
CONF_MIN_BRIGHTNESS_CHANGE = "min_brightness_change"
CONF_MIN_COLOR_TEMP_CHANGE = "min_color_temp_change"
DEFAULT_MIN_BRIGHTNESS_CHANGE = 5
DEFAULT_MIN_COLOR_TEMP_CHANGE = 5

# Options keys: how often each area ticks (minutes) and the spacing between
# areas (seconds).
CONF_TICK_INTERVAL = "tick_interval"
CONF_TICK_GAP = "tick_gap"
DEFAULT_TICK_INTERVAL = 1
DEFAULT_TICK_GAP = 1

# The Clear button's role (its unique ID's suffix and translation key) and
# the object ID it's created with.
CLEAR_ROLE = "clear"
CLEAR_OBJECT_ID = "flare_clear"

# The event FLARE fires for each area in turn, which the blueprint listens for.
EVENT_TYPE_TICK = "flare_tick"

SCHEDULES_ENTRY_TITLE = "Schedules"
SETTINGS_ENTRY_TITLE = "Settings"
FLARES_ENTRY_TITLE = "Flares"
