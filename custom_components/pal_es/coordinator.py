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
    EVENT_RETRY_DELAY,
    MQTT_FALLBACK_INTERVAL,
    POST_OPEN_REFRESH_DELAYS,
)

_LOGGER = logging.getLogger(__name__)

_INPUT_KEY = re.compile(r"^in(\d+)Status$")

def _parse_inputs(source: dict[str, Any]) -> dict[int, str | None]:
    inputs: dict[int, str | None] = {}
    for key, value in source.items():
        if m := _INPUT_KEY.match(key):
            inputs[int(m.group(1))] = value
    return inputs


type PalConfigEntry = ConfigEntry[PalCoordinator]


class PalCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls the input status of the devices the user selected.

    Normally the portal pushes an MQTT event when a device reports something;
    that triggers a read of just that device. The regular poll then only runs
    as a rare safety net (MQTT_FALLBACK_INTERVAL) and at the configured
    polling interval while MQTT is not connected.

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
        self._poll_interval = timedelta(seconds=interval)
        self._event_timers: dict[str, list[CALLBACK_TYPE]] = {}
        self.mqtt_connected = False

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
            result[dev_id] = {"info": info, "inputs": _parse_inputs(source)}
        return result

    # ------------------------------------------------------------------ MQTT
    def set_mqtt_connected(self, connected: bool) -> None:
        """Slow the regular poll down while push events are available."""
        was = self.mqtt_connected
        self.mqtt_connected = connected
        if connected:
            self.update_interval = max(
                self._poll_interval, timedelta(seconds=MQTT_FALLBACK_INTERVAL)
            )
            if not was:  # resync: events may have been missed while offline
                self.hass.async_create_task(self.async_request_refresh())
        else:
            self.update_interval = self._poll_interval
        _LOGGER.debug("MQTT %s, poll interval %s", "connected" if connected else "down", self.update_interval)

    def handle_device_event(self, device_id: str) -> None:
        """The portal reported something for a device: read its input status now."""
        if device_id not in self.selected_ids or self.data is None:
            return
        for cancel in self._event_timers.pop(device_id, []):
            cancel()
        self.hass.async_create_task(self._async_refresh_device(device_id, retry=True))

    async def _async_refresh_device(self, device_id: str, retry: bool = False) -> None:
        current = (self.data or {}).get(device_id)
        if current is None:
            return
        try:
            status = await self.api.async_get_input_status(device_id)
        except PalApiError as err:
            _LOGGER.debug("Status of %s after MQTT event failed: %s", device_id, err)
            await self.async_request_refresh()
            return
        inputs = _parse_inputs(status)
        if inputs and inputs != current["inputs"]:
            data = dict(self.data)
            data[device_id] = {"info": current["info"], "inputs": inputs}
            self.async_set_updated_data(data)
        elif retry:
            # Unchanged: the portal may not have processed the event yet. One more look.
            async def _again(_now: Any) -> None:
                await self._async_refresh_device(device_id)

            self._event_timers[device_id] = [
                async_call_later(self.hass, EVENT_RETRY_DELAY, _again)
            ]

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
        for timers in self._event_timers.values():
            for cancel in timers:
                cancel()
        self._event_timers = {}
