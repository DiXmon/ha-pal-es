"""Diagnostics with personal data redacted (safe to attach to GitHub issues)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import PalConfigEntry

TO_REDACT = {
    "username",
    "password",
    "token",
    "pass",
    "wifi",
    "imei",
    "iccid",
    "phoneNumber",
    "address",
    "initConfirmation",
    "orgs",
    "serial_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PalConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "devices": {
            f"device_{i}": {
                "inputs": item["inputs"],
                "info": async_redact_data(item["info"], TO_REDACT),
            }
            for i, item in enumerate(coordinator.data.values(), start=1)
        },
    }
