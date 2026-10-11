"""Pure helpers without Home Assistant imports, so they can be unit-tested."""
from __future__ import annotations

from typing import Any, Literal

from .const import (
    CONF_ICON_TYPE,
    CONF_INVERT,
    CONF_OUTPUT_INVERT,
    CONF_OUTPUTS,
    DEFAULT_ICON_TYPE,
    ICONS,
)

GateState = Literal["open", "closed", "unknown"]

# Values the portal reports for an input.
INPUT_ACTIVE = "active"
INPUT_IDLE = "idle"


def output_key(device_id: str, output: int) -> str:
    return f"{device_id}:{output}"


def output_settings(options: dict[str, Any], device_id: str, output: int) -> dict[str, Any]:
    """Settings of one output: icon type and input polarity.

    Polarity: invert=False means input "active" = closed, "idle" = open
    (normally-open reed sensor closed by the gate). invert=True is the opposite.
    The 0.2.x global option is used as the default.
    """
    cfg = (options.get(CONF_OUTPUTS) or {}).get(output_key(device_id, output)) or {}
    icon_type = cfg.get(CONF_ICON_TYPE)
    if icon_type not in ICONS:
        icon_type = DEFAULT_ICON_TYPE
    invert = cfg.get(CONF_OUTPUT_INVERT, options.get(CONF_INVERT, False))
    return {CONF_ICON_TYPE: icon_type, CONF_OUTPUT_INVERT: bool(invert)}


def gate_state(raw: str | None, invert: bool) -> GateState:
    if raw not in (INPUT_ACTIVE, INPUT_IDLE):
        return "unknown"
    closed = raw == INPUT_ACTIVE
    if invert:
        closed = not closed
    return "closed" if closed else "open"


def gate_icon(icon_type: str, state: GateState) -> str:
    closed_icon, open_icon = ICONS.get(icon_type, ICONS[DEFAULT_ICON_TYPE])
    return open_icon if state == "open" else closed_icon
