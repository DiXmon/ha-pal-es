"""Tests for the MQTT client against a fake broker (no network, no Home Assistant)."""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

PKG_DIR = Path(__file__).parent.parent / "custom_components" / "pal_es"
pkg = types.ModuleType("pal_es_test_mqtt")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["pal_es_test_mqtt"] = pkg
mq = importlib.import_module("pal_es_test_mqtt.mqtt")
const = importlib.import_module("pal_es_test_mqtt.const")


def test_device_from_topic():
    assert mq.device_from_topic("org/13680/evt/device/4G610204136/log") == "4G610204136"
    assert mq.device_from_topic("org/1/evt/other") is None
    assert mq.device_from_topic("admin/a@b/evt/device/x/y") is None


def test_pop_packets_split_and_joined():
    pkt = mq.build_packet(0x30, b"\x00\x01a")  # PUBLISH topic "a"
    buf = bytearray(pkt + pkt[:2])
    got = mq.pop_packets(buf)
    assert len(got) == 1 and got[0][0] == mq.PUBLISH
    buf += pkt[2:]
    assert len(mq.pop_packets(buf)) == 1 and not buf


def test_remaining_length_multibyte():
    body = b"x" * 300
    buf = bytearray(mq.build_packet(0x30, body))
    (ptype, _f, out), = mq.pop_packets(buf)
    assert out == body


class FakeApi:
    def __init__(self, port_url: str):
        self.calls = 0

    async def async_get_mqtt_credentials(self):
        self.calls += 1
        return "tok", "13680", None


class FakeBroker:
    def __init__(self):
        self.connect_body = None
        self.sub_topic = None
        self.deny = False

    async def handler(self, req: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(protocols=("mqtt",))
        await ws.prepare(req)
        buf = bytearray()
        async for msg in ws:
            buf += msg.data
            for ptype, flags, body in mq.pop_packets(buf):
                if ptype == mq.CONNECT:
                    self.connect_body = body
                    await ws.send_bytes(b"\x20\x02\x00\x00")
                elif ptype == mq.SUBSCRIBE:
                    tlen = int.from_bytes(body[2:4], "big")
                    self.sub_topic = body[4 : 4 + tlen].decode()
                    await ws.send_bytes(mq.build_packet(0x90, body[:2] + (b"\x80" if self.deny else b"\x00")))
                    if not self.deny:
                        t = b"org/13680/evt/device/DEV1/log"
                        await ws.send_bytes(mq.build_packet(0x30, len(t).to_bytes(2, "big") + t))
        return ws


def test_client_receives_events():
    async def run():
        broker = FakeBroker()
        app = web.Application()
        app.router.add_get("/mqtt", broker.handler)
        server = TestServer(app)
        await server.start_server()
        mq.MQTT_URL = f"http://127.0.0.1:{server.port}/mqtt"
        events, states = [], []
        async with aiohttp.ClientSession() as session:
            client = mq.PalMqtt(session, FakeApi(""), events.append, states.append)
            task = asyncio.create_task(client.async_run())
            for _ in range(50):
                if events:
                    break
                await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await server.close()
        assert events == ["DEV1"]
        assert states == [True, False]
        assert broker.sub_topic == "org/13680/#"
        assert b"adminApp" in broker.connect_body and b"tok" in broker.connect_body

    asyncio.run(run())


def test_denied_subscription_is_not_connected():
    async def run():
        broker = FakeBroker()
        broker.deny = True
        app = web.Application()
        app.router.add_get("/mqtt", broker.handler)
        server = TestServer(app)
        await server.start_server()
        mq.MQTT_URL = f"http://127.0.0.1:{server.port}/mqtt"
        states = []
        async with aiohttp.ClientSession() as session:
            client = mq.PalMqtt(session, FakeApi(""), lambda d: None, states.append)
            task = asyncio.create_task(client.async_run())
            await asyncio.sleep(0.6)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await server.close()
        assert True not in states

    asyncio.run(run())
