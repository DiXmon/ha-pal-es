"""Config flow: login, then pick which devices to expose."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import PalApi, PalApiError, PalAuthError
from .const import (
    CONF_DEVICES,
    CONF_INVERT,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import PalConfigEntry


def _device_label(dev: dict[str, Any]) -> str:
    parts = [dev.get("name"), dev.get("name1")]
    title = " / ".join(p for p in parts if p) or dev["_id"]
    return f"{title} ({dev['_id']})"


def _device_selector(devices: list[dict[str, Any]]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=d["_id"], label=_device_label(d)) for d in devices
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


class PalConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._devices: list[dict[str, Any]] = []

    async def _login_and_list(self) -> str | None:
        """Return an error key or None."""
        api = PalApi(async_get_clientsession(self.hass), self._username, self._password)
        try:
            await api.async_login()
            self._devices = await api.async_get_devices()
        except PalAuthError:
            return "invalid_auth"
        except PalApiError:
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            self._password = user_input[CONF_PASSWORD]
            await self.async_set_unique_id(self._username.lower())
            self._abort_if_unique_id_configured()
            if err := await self._login_and_list():
                errors["base"] = err
            elif not self._devices:
                errors["base"] = "no_devices"
            else:
                return await self.async_step_devices()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
            ),
            errors=errors,
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_DEVICES]:
                errors["base"] = "select_one"
            else:
                return self.async_create_entry(
                    title=self._username,
                    data={CONF_USERNAME: self._username, CONF_PASSWORD: self._password},
                    options={CONF_DEVICES: user_input[CONF_DEVICES]},
                )
        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICES): _device_selector(self._devices)}
            ),
            errors=errors,
        )

    # ---------------------------------------------------------------- reauth
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._username = entry_data[CONF_USERNAME]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._password = user_input[CONF_PASSWORD]
            if err := await self._login_and_list():
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_PASSWORD: self._password},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": self._username},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: PalConfigEntry) -> OptionsFlow:
        return PalOptionsFlow()


class PalOptionsFlow(OptionsFlow):
    """Change the exposed devices, polling interval, input polarity."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry: PalConfigEntry = self.config_entry
        errors: dict[str, str] = {}

        api = PalApi(
            async_get_clientsession(self.hass),
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
        )
        try:
            devices = await api.async_get_devices()
        except PalApiError:
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            if not user_input[CONF_DEVICES]:
                errors["base"] = "select_one"
            else:
                return self.async_create_entry(data=user_input)

        opts = entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICES, default=opts.get(CONF_DEVICES, [])
                ): _device_selector(devices),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
                vol.Required(CONF_INVERT, default=opts.get(CONF_INVERT, False)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
