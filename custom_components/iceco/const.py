"""Constants for Iceco integration."""

DOMAIN = "iceco"

# Configuration keys
CONF_DEVICE_ADDRESS = "device_address"

# Options keys (user-configurable)
CONF_POLL_INTERVAL = "poll_interval"
CONF_POWER_LOSS_TIMEOUT = "power_loss_timeout"
CONF_TEMP_DEVIATION_THRESHOLD = "temp_deviation_threshold"
CONF_TEMP_DEVIATION_DURATION = "temp_deviation_duration"

# Default values
DEFAULT_POLL_INTERVAL = 60  # seconds
DEFAULT_POWER_LOSS_TIMEOUT = 15  # minutes (lowered from 30 for faster alerts)
DEFAULT_TEMP_DEVIATION_THRESHOLD = 5  # degrees Celsius
DEFAULT_TEMP_DEVIATION_DURATION = 5  # minutes (lowered from 15 for faster alerts)

# Validation ranges
MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 300
MIN_POWER_LOSS_TIMEOUT = 10
MAX_POWER_LOSS_TIMEOUT = 120
MIN_TEMP_DEVIATION_THRESHOLD = 1
MAX_TEMP_DEVIATION_THRESHOLD = 10
MIN_TEMP_DEVIATION_DURATION = 5
MAX_TEMP_DEVIATION_DURATION = 60

# Entity unique ID suffixes
ENTITY_CLIMATE_LEFT = "climate_left"
ENTITY_CLIMATE_RIGHT = "climate_right"
ENTITY_BATTERY_VOLTAGE = "battery_voltage"
ENTITY_POWER_LOSS_ALARM = "power_loss_alarm"
ENTITY_TEMP_ALARM_LEFT = "temp_alarm_left"
ENTITY_TEMP_ALARM_RIGHT = "temp_alarm_right"
ENTITY_POWER_SWITCH = "power_switch"
ENTITY_ECO_MODE = "eco_mode"
ENTITY_LOCK = "lock"
ENTITY_CONNECTION = "connection"

# Attribute keys
ATTR_BATTERY_PROTECTION_LEVEL = "battery_protection_level"
ATTR_LAST_UPDATE = "last_update"
ATTR_CONNECTION_STATE = "connection_state"
ATTR_SET_TEMPERATURE = "set_temperature"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_DEVIATION = "deviation"
ATTR_THRESHOLD = "threshold"
ATTR_TIMEOUT_MINUTES = "timeout_minutes"

# Temperature limits (Celsius — HA auto-converts for display)
MIN_TEMP = -22  # °C
MAX_TEMP = 10   # °C
TEMP_STEP = 1

# Hysteresis for alarm clearing (degrees Celsius)
ALARM_HYSTERESIS = 2
