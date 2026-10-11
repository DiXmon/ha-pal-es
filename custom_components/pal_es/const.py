"""Constants for the PAL portal integration."""
from __future__ import annotations

DOMAIN = "pal_es"

BASE_URL = "https://portal.pal-es.com/api1"

CONF_DEVICES = "devices"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INVERT = "invert_input"

DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 3
MAX_SCAN_INTERVAL = 300

# Minimum seconds between a login and a login forced by a rejected request.
RELOGIN_COOLDOWN = 30

# Re-login when the token has less than this many seconds left.
TOKEN_REFRESH_MARGIN = 300

# After pressing "open", refresh the input status after these delays (seconds).
POST_OPEN_REFRESH_DELAYS = (3, 8)
