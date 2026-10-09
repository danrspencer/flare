from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

DOMAIN = "flare"

# What HA reports for an entity it can't reach, or hasn't heard from yet.
UNREACHABLE_STATES = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})


def is_reachable(state: State | None) -> bool:
    """Whether HA has a real state for an entity: it exists, and isn't
    unavailable or unknown. Every check of reachability goes through this."""
    return state is not None and state.state not in UNREACHABLE_STATES


PHASES = ["Morning", "Day", "Evening", "Night"]
PHASE_OPTIONS = ["Auto", *PHASES]

# Subentry type for a schedule sensor.
SUBENTRY_TYPE_SENSOR = "sensor"

# Options key: bulb models needing two-step transitions (see two_step.py).
CONF_TWO_STEP_MODELS = "two_step_models"

# Subentry type for a zone. The value is stored in every install's zones,
# and HA can't change a subentry's type, so it stays "state".
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
ENTRY_TYPE_ZONES = "tracking"
ENTRY_TYPE_FLARES = "flares"

# Subentry type for a flare: a light that runs an automation.
SUBENTRY_TYPE_FLARE = "flare"

# A flare's subentry data.
CONF_AUTOMATION = "automation"  # entity registry id, which survives renames
CONF_LIGHTS_INPUT = "lights_input"  # the blueprint input holding the lights
CONF_LIGHTS_INPUT_KIND = "lights_input_kind"  # "target", or the target key its value is
CONF_LIGHTS_TARGET = "lights_target"  # a plain automation's lights, as a target
CONF_ZONE_INPUT = "zone_input"  # the blueprint input holding the zone device
CONF_AREA = "area_id"  # where the flare's device starts out

# Our blueprint's inputs naming the room's lights and its zone.
BLUEPRINT_LIGHTS_INPUT = "room_target"
BLUEPRINT_ZONE_INPUT = "zone"

# Options keys: the smallest change apply_lighting sends, as a percentage
# of the target brightness and in mireds of colour temperature.
CONF_MIN_BRIGHTNESS_CHANGE = "min_brightness_change"
CONF_MIN_COLOR_TEMP_CHANGE = "min_color_temp_change"
DEFAULT_MIN_BRIGHTNESS_CHANGE = 5
DEFAULT_MIN_COLOR_TEMP_CHANGE = 5

# Options keys: how often each zone ticks (minutes) and the spacing between
# zones (seconds).
CONF_TICK_INTERVAL = "tick_interval"
CONF_TICK_GAP = "tick_gap"
DEFAULT_TICK_INTERVAL = 1
DEFAULT_TICK_GAP = 1

# The event_type a zone's tick entity fires, which the blueprint listens for.
EVENT_TYPE_TICK = "flare_tick"

SCHEDULES_ENTRY_TITLE = "Schedules"
ZONES_ENTRY_TITLE = "Zones"
FLARES_ENTRY_TITLE = "Flares"
