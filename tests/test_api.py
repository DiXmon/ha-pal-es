"""Tests for the PAL API client against a fake PAL portal (no network, no Home Assistant).

The package __init__ imports Home Assistant, so we register a bare package
that points at the integration directory and import only api.py / const.py.
"""
from __future__ import annotations

import asyncio
import base64
import importlib
import json
import sys
import time
import types
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

PKG_DIR = Path(__file__).parent.parent / "custom_components" / "pal_es"

pkg = types.ModuleType("pal_es_test")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["pal_es_test"] = pkg
api_mod = importlib.import_module("pal_es_test.api")
PalApi, PalApiError, PalAuthError = api_mod.PalApi, api_mod.PalApiError, api_mod.PalAuthError


def make_jwt(exp_ms: int) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS512'})}.{b64({'exp': exp_ms, 'id': 'u'})}.sig"


class FakePortal:
    def __init__(self) -> None:
        self.logins = 0
        self.tokens: list[str] = []
        self.fail_next_with_401 = False
        self.fail_next_with_err = False  # HTTP 200 with an "err" body
        self.gate_confirmed = True
        self.opened: list[tuple[str, dict]] = []
        self.token_exp_ms = int((time.time() + 86400) * 1000)
        self.input = "active"

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/api1/user/login1", self.login)
        app.router.add_get("/api1/devices", self.devices)
        app.router.add_get("/api1/device/{id}/get-input-status", self.input_status)
        app.router.add_post("/api1/device/{id}/open-gate", self.open_gate)
        return app

    async def login(self, req: web.Request) -> web.Response:
        body = await req.json()
        if body.get("password") != "secret":
            return web.json_response({"err": "x", "errId": 5, "msg": "Wrong credentials"})
        self.logins += 1
        token = make_jwt(self.token_exp_ms) + str(self.logins)
        self.tokens.append(token)
        return web.json_response({"err": None, "errId": 0, "user": {"token": token}})

    def _auth(self, req: web.Request) -> bool:
        if self.fail_next_with_401:
            self.fail_next_with_401 = False
            return False
        return req.headers.get("X-Access-Token") == (self.tokens[-1] if self.tokens else None)

    def _soft_error(self) -> web.Response | None:
        if self.fail_next_with_err:
            self.fail_next_with_err = False
            return web.json_response({"err": "token", "errId": 9, "msg": "Invalid token"})
        return None

    async def devices(self, req: web.Request) -> web.Response:
        if not self._auth(req):
            return web.json_response({"err": "auth"}, status=401)
        if (soft := self._soft_error()) is not None:
            return soft
        return web.json_response(
            {
                "err": None,
                "devices": {
                    "list": [
                        {"_id": "4G610204136", "name": "Ewatrade", "name1": "Szlaban",
                         "outputs": 1, "connected": True, "in1Status": self.input}
                    ]
                },
            }
        )

    async def input_status(self, req: web.Request) -> web.Response:
        if not self._auth(req):
            return web.json_response({"err": "auth"}, status=401)
        return web.json_response({"err": None, "msg": "success", "in1Status": self.input})

    async def open_gate(self, req: web.Request) -> web.Response:
        if not self._auth(req):
            return web.json_response({"err": "auth"}, status=401)
        if (soft := self._soft_error()) is not None:
            return soft
        self.opened.append((req.match_info["id"], await req.json()))
        return web.json_response(
            {"err": None, "msg": f"Gate opened: {self.gate_confirmed}", "confirmed": self.gate_confirmed}
        )


def run(coro_fn):
    """Run `coro_fn(portal, api)` with a fake server and a patched BASE_URL."""

    async def _inner():
        portal = FakePortal()
        server = TestServer(portal.app())
        await server.start_server()
        api_mod.BASE_URL = str(server.make_url("/api1"))
        async with aiohttp.ClientSession() as session:
            api = PalApi(session, "user@example.com", "secret")
            try:
                await coro_fn(portal, api)
            finally:
                await server.close()

    asyncio.run(_inner())


def test_login_list_status_open():
    async def go(portal, api):
        devices = await api.async_get_devices()
        assert [d["_id"] for d in devices] == ["4G610204136"]
        status = await api.async_get_input_status("4G610204136")
        assert status["in1Status"] == "active"
        await api.async_open_gate("4G610204136", 1)
        assert portal.opened == [("4G610204136", {"output": "1"})]
        assert portal.logins == 1  # token is reused

    run(go)


def test_wrong_password():
    async def go(portal, api):
        bad = PalApi(api._session, "user@example.com", "nope")
        with pytest.raises(PalAuthError):
            await bad.async_get_devices()

    run(go)


def test_relogin_after_401():
    async def go(portal, api):
        api._relogin_cooldown = 0
        await api.async_get_devices()
        assert portal.logins == 1
        portal.fail_next_with_401 = True
        await api.async_get_devices()  # server rejects once -> client logs in again
        assert portal.logins == 2

    run(go)


def test_get_relogin_on_soft_error_in_200_body():
    async def go(portal, api):
        api._relogin_cooldown = 0
        await api.async_get_devices()
        portal.fail_next_with_err = True  # revoked token reported as HTTP 200 + err
        devices = await api.async_get_devices()
        assert devices and portal.logins == 2

    run(go)


def test_post_is_never_retried_on_soft_error():
    async def go(portal, api):
        api._relogin_cooldown = 0
        await api.async_get_devices()
        portal.fail_next_with_err = True
        with pytest.raises(PalApiError):
            await api.async_open_gate("4G610204136", 1)
        assert portal.opened == []  # not repeated
        assert portal.logins == 1

    run(go)


def test_cooldown_prevents_login_storm():
    async def go(portal, api):
        await api.async_get_devices()  # fresh login, default 30 s cooldown active
        portal.fail_next_with_401 = True
        with pytest.raises(PalApiError):
            await api.async_get_devices()
        assert portal.logins == 1  # no second login right after the first

    run(go)


def test_expired_token_refreshed_before_request():
    async def go(portal, api):
        portal.token_exp_ms = int((time.time() + 60) * 1000)  # < 5 min margin
        await api.async_get_devices()
        await api.async_get_devices()
        assert portal.logins == 2

    run(go)


def test_open_not_confirmed_raises():
    async def go(portal, api):
        portal.gate_confirmed = False
        with pytest.raises(PalApiError):
            await api.async_open_gate("4G610204136", 1)

    run(go)


def test_connection_error_is_api_error():
    async def go(portal, api):
        api_mod.BASE_URL = "http://127.0.0.1:1/api1"
        with pytest.raises(PalApiError):
            await api.async_get_devices()

    run(go)
