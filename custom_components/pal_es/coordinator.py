"""Data coordinator for the PAL portal integration."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PalApi, PalApiError, PalAuthError
from .const import (
    CONF_DEVICES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POST_OPEN_REFRESH_DELAYS,
)

_LOGGER = logging.getLogger(__name__)

_INPUT_KEY = re.compile(r"^in(\d+)Status$")

type PalConfigEntry = ConfigEntry[PalCoordinator]


class PalCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls only the devices the user selected.

    data[device_id] = {"info": <device dict from /devices>, "inputs": {1: "active", ...}}
    """

    config_entry: PalConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PalConfigEntry, api: PalApi) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self._pending: list[CALLBACK_TYPE] = []

    @property
    def selected_ids(self) -> list[str]:
        opts = self.config_entry.options
        return list(opts.get(CONF_DEVICES, self.config_entry.data.get(CONF_DEVICES, [])))

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        selected = self.selected_ids
        try:
            devices = await self.api.async_get_devices()
            by_id = {d.get("_id"): d for d in devices}
            targets = [i for i in selected if i in by_id]
            statuses = await asyncio.gather(
                *(self.api.async_get_input_status(i) for i in targets),
                return_exceptions=True,
            )
        except PalAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PalApiError as err:
            raise UpdateFailed(str(err)) from err

        result: dict[str, dict[str, Any]] = {}
        for dev_id, status in zip(targets, statuses):
            info = by_id[dev_id]
            if isinstance(status, PalAuthError):
                raise ConfigEntryAuthFailed(str(status))
            inputs: dict[int, str | None] = {}
            if isinstance(status, Exception):
                _LOGGER.debug("Input status for %s failed: %s", dev_id, status)
                # fall back to the (possibly stale) value from the device list
                source: dict[str, Any] = info
            else:
                source = status
            for key, value in source.items():
                if m := _INPUT_KEY.match(key):
                    inputs[int(m.group(1))] = value
            result[dev_id] = {"info": info, "inputs": inputs}
        return result

    def schedule_refreshes_after_open(self) -> None:
        """Poll a bit faster right after a gate was triggered."""
        for cancel in self._pending:
            cancel()
        self._pending = []

        async def _refresh(_now: Any) -> None:
            await self.async_request_refresh()

        for delay in POST_OPEN_REFRESH_DELAYS:
            self._pending.append(async_call_later(self.hass, delay, _refresh))

    def cancel_pending(self) -> None:
        for cancel in self._pending:
            cancel()
        self._pending = []
