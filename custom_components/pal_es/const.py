"""Constants for the PAL portal integration."""
from __future__ import annotations

DOMAIN = "pal_es"

BASE_URL = "https://portal.pal-es.com/api1"

CONF_DEVICES = "devices"
CONF_SCAN_INTERVAL = "scan_interval"
# Per-output settings live in options[CONF_OUTPUTS]["<device_id>:<output>"].
CONF_OUTPUTS = "outputs"
CONF_ICON_TYPE = "icon_type"
CONF_OUTPUT_INVERT = "invert"
# Legacy global option from 0.2.x; only used as the default for outputs.
CONF_INVERT = "invert_input"

DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 3
MAX_SCAN_INTERVAL = 300

# The device list (names, connected flag) changes rarely: refresh it this often.
DEVICE_LIST_REFRESH = 300  # seconds

# Minimum seconds between a login and a login forced by a rejected request.
RELOGIN_COOLDOWN = 30

# Re-login when the token has less than this many seconds left.
TOKEN_REFRESH_MARGIN = 300

# After pressing "open", refresh the input status after these delays (seconds).
POST_OPEN_REFRESH_DELAYS = (3, 8)

# icon type -> (icon when closed/unknown, icon when open)
ICONS: dict[str, tuple[str, str]] = {
    "swing_gate": ("mdi:gate", "mdi:gate-open"),
    "garage_door": ("mdi:garage", "mdi:garage-open"),
    "barrier": ("mdi:boom-gate", "mdi:boom-gate-up"),
}
DEFAULT_ICON_TYPE = "swing_gate"

# MQTT push (the portal publishes an event when a device reports something).
MQTT_URL = "wss://portal.pal-es.com/mqtt"
MQTT_ORIGIN = "https://portal.pal-es.com"
MQTT_USERNAME = "adminApp"  # the portal's web app logs in with this user name + the API token
MQTT_KEEPALIVE = 30
# While MQTT is connected, poll only this rarely (safety net for missed events).
MQTT_FALLBACK_INTERVAL = 300
# After an MQTT event the input status is read at once; if it has not changed yet
# (the portal may update it a moment later) it is read once more after this delay (s).
EVENT_RETRY_DELAY = 3
