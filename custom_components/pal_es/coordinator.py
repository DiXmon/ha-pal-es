"""Data coordinator for the PAL portal integration."""
from __future__ import annotations

import asyncio
import logging
import re
import time
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
    DEVICE_LIST_REFRESH,
    DOMAIN,
    POST_OPEN_REFRESH_DELAYS,
)

_LOGGER = logging.getLogger(__name__)

_INPUT_KEY = re.compile(r"^in(\d+)Status$")

type PalConfigEntry = ConfigEntry[PalCoordinator]


class PalCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls the input status of the devices the user selected.

    Every poll costs one request per selected device (get-input-status). The
    device list (names, connected flag) is fetched at start and then only every
    DEVICE_LIST_REFRESH seconds, or right away when a status request failed
    (the list also carries in*Status and serves as fallback).

    data[device_id] = {"info": <device dict>, "inputs": {1: "active", ...}}
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
        self._devices: dict[str, dict[str, Any]] | None = None
        self._devices_at: float = 0.0

    @property
    def selected_ids(self) -> list[str]:
        opts = self.config_entry.options
        return list(opts.get(CONF_DEVICES, self.config_entry.data.get(CONF_DEVICES, [])))

    async def _refresh_devices(self) -> dict[str, dict[str, Any]]:
        devices = await self.api.async_get_devices()
        self._devices = {d["_id"]: d for d in devices if d.get("_id")}
        self._devices_at = time.monotonic()
        return self._devices

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        selected = self.selected_ids
        try:
            devices = self._devices
            if devices is None or time.monotonic() - self._devices_at > DEVICE_LIST_REFRESH:
                devices = await self._refresh_devices()

            targets = [i for i in selected if i in devices]
            statuses = list(
                await asyncio.gather(
                    *(self.api.async_get_input_status(i) for i in targets),
                    return_exceptions=True,
                )
            )
            for status in statuses:
                if isinstance(status, PalAuthError):
                    raise status
            if any(isinstance(s, Exception) for s in statuses):
                _LOGGER.debug("Some status requests failed, falling back to device list")
                devices = await self._refresh_devices()
        except PalAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PalApiError as err:
            raise UpdateFailed(str(err)) from err

        result: dict[str, dict[str, Any]] = {}
        for dev_id, status in zip(targets, statuses):
            info = devices.get(dev_id)
            if info is None:
                continue
            source: dict[str, Any] = info if isinstance(status, Exception) else status
            inputs: dict[int, str | None] = {}
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
