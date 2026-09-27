DOMAIN = "flare"

PHASE_OPTIONS = ["Auto", "Morning", "Day", "Evening", "Night"]

# Subentry type for a schedule sensor.
SUBENTRY_TYPE_SENSOR = "sensor"

# Options key: bulb models needing two-step transitions (see two_step.py).
CONF_TWO_STEP_MODELS = "two_step_models"

# Subentry type for a state device (a tracking scope).
SUBENTRY_TYPE_STATE = "state"

# A state device's target. Only used to place its device in an area; it
# doesn't decide which lights the scope tracks.
CONF_TARGET = "target"

# Fired when a tracked light becomes "overridden", with both claims and
# the live values at that moment (see sensor.py's _refresh_statuses).
EVENT_LIGHT_OVERRIDDEN = "flare_light_overridden"

# Two config entries rather than one, because HA's integration page can't
# group subentries by type.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_SCHEDULES = "schedules"
ENTRY_TYPE_TRACKING = "tracking"

# Options keys: the smallest change apply_lighting sends, as a percentage
# of the target brightness and in mireds of colour temperature.
CONF_MIN_BRIGHTNESS_CHANGE = "min_brightness_change"
CONF_MIN_COLOR_TEMP_CHANGE = "min_color_temp_change"
DEFAULT_MIN_BRIGHTNESS_CHANGE = 5
DEFAULT_MIN_COLOR_TEMP_CHANGE = 5
