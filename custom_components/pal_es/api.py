"""Minimal async client for the PAL portal API (portal.pal-es.com/api1)."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

import aiohttp

from .const import BASE_URL, TOKEN_REFRESH_MARGIN

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=20)


class PalApiError(Exception):
    """Generic API / connection error."""


class PalAuthError(PalApiError):
    """Login rejected."""


def _jwt_exp_seconds(token: str) -> float | None:
    """Return token expiry (epoch seconds). The portal puts `exp` in milliseconds."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
        return exp / 1000 if exp > 1e11 else float(exp)
    except Exception:  # noqa: BLE001
        return None


class PalApi:
    """Handles login, token refresh and the few calls we need."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_exp: float | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth
    async def async_login(self) -> None:
        """Log in and store the token."""
        try:
            async with self._session.post(
                f"{BASE_URL}/user/login1",
                json={"username": self._username, "password": self._password, "b": ""},
                headers={"Accept": "application/json, text/plain, */*"},
                timeout=_TIMEOUT,
            ) as resp:
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise PalApiError(f"Cannot reach PAL portal: {err}") from err

        token = (data or {}).get("user", {}).get("token") if isinstance(data, dict) else None
        if not token:
            msg = data.get("msg") if isinstance(data, dict) else "login failed"
            raise PalAuthError(msg or "login failed")
        self._token = token
        self._token_exp = _jwt_exp_seconds(token)

    def _token_valid(self) -> bool:
        if not self._token:
            return False
        if self._token_exp is None:
            return True
        return self._token_exp - time.time() > TOKEN_REFRESH_MARGIN

    async def _ensure_token(self) -> None:
        if self._token_valid():
            return
        async with self._lock:
            if not self._token_valid():
                await self.async_login()

    # --------------------------------------------------------------- requests
    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        _retry: bool = True,
    ) -> dict[str, Any]:
        await self._ensure_token()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "X-Access-Token": self._token or "",
            "X-Pal-P-T": "",
        }
        try:
            async with self._session.request(
                method,
                f"{BASE_URL}{path}",
                json=body,
                headers=headers,
                timeout=_TIMEOUT,
            ) as resp:
                status = resp.status
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise PalApiError(f"Request {path} failed: {err}") from err

        if status in (401, 403) and _retry:
            self._token = None  # force fresh login
            return await self._request(method, path, body, _retry=False)
        if status >= 400:
            raise PalApiError(f"HTTP {status} for {path}")
        if not isinstance(data, dict):
            raise PalApiError(f"Unexpected response for {path}")
        if data.get("err"):
            raise PalApiError(f"{path}: {data.get('msg') or data.get('err')}")
        return data

    # -------------------------------------------------------------------- API
    async def async_get_devices(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/devices")
        return list((data.get("devices") or {}).get("list") or [])

    async def async_get_input_status(self, device_id: str) -> dict[str, Any]:
        """Return the raw reply; contains in1Status, in2Status... keys."""
        from urllib.parse import quote

        return await self._request(
            "GET", f"/device/{quote(device_id, safe='')}/get-input-status"
        )

    async def async_open_gate(self, device_id: str, output: int = 1) -> None:
        from urllib.parse import quote

        data = await self._request(
            "POST",
            f"/device/{quote(device_id, safe='')}/open-gate",
            {"output": str(output)},
        )
        if data.get("confirmed") is False:
            raise PalApiError(data.get("msg") or "Gate open not confirmed")
