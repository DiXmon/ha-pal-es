"""Tiny MQTT 3.1.1 client over WebSocket for the PAL portal's event stream.

Only what is needed: CONNECT, SUBSCRIBE (QoS 0), receive PUBLISH, keep-alive.
No Home Assistant imports, so it can be tested on its own.

The portal publishes e.g. `org/<orgId>/evt/device/<deviceId>/log` (empty payload)
whenever a device reports something. We only use the topic as a "something
happened on this device" signal; the state itself is then read over the HTTP API.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable

import aiohttp

from .api import PalApi, PalApiError
from .const import (
    MQTT_KEEPALIVE,
    MQTT_ORIGIN,
    MQTT_URL,
    MQTT_USERNAME,
)

_LOGGER = logging.getLogger(__name__)

CONNECT, CONNACK, PUBLISH, PUBACK, SUBSCRIBE, SUBACK, PINGREQ, PINGRESP = (
    1, 2, 3, 4, 8, 9, 12, 13,
)


class MqttError(Exception):
    """Connection / protocol problem."""


def _utf8(value: str) -> bytes:
    raw = value.encode()
    return len(raw).to_bytes(2, "big") + raw


def _remaining_length(n: int) -> bytes:
    out = bytearray()
    while True:
        digit = n % 128
        n //= 128
        out.append(digit | 0x80 if n else digit)
        if not n:
            return bytes(out)


def build_packet(first_byte: int, body: bytes = b"") -> bytes:
    return bytes([first_byte]) + _remaining_length(len(body)) + body


def build_connect(client_id: str, username: str, password: str, keepalive: int) -> bytes:
    body = (
        _utf8("MQTT")
        + bytes([4, 0xC2])  # level 4 (3.1.1); flags: user name, password, clean session
        + keepalive.to_bytes(2, "big")
        + _utf8(client_id)
        + _utf8(username)
        + _utf8(password)
    )
    return build_packet(CONNECT << 4, body)


def build_subscribe(packet_id: int, topic: str) -> bytes:
    body = packet_id.to_bytes(2, "big") + _utf8(topic) + b"\x00"
    return build_packet((SUBSCRIBE << 4) | 0x02, body)


def pop_packets(buf: bytearray) -> list[tuple[int, int, bytes]]:
    """Remove all complete packets from buf; return (type, flags, body) tuples."""
    packets: list[tuple[int, int, bytes]] = []
    while len(buf) >= 2:
        length = 0
        mult = 1
        i = 1
        while True:
            if i >= len(buf):
                return packets  # length bytes incomplete
            byte = buf[i]
            length += (byte & 0x7F) * mult
            i += 1
            if not byte & 0x80:
                break
            mult *= 128
            if mult > 128**3:
                raise MqttError("bad remaining length")
        if len(buf) < i + length:
            return packets
        first = buf[0]
        packets.append((first >> 4, first & 0x0F, bytes(buf[i : i + length])))
        del buf[: i + length]
    return packets


def parse_publish(flags: int, body: bytes) -> tuple[str, bytes, int | None]:
    """Return (topic, payload, packet id when QoS > 0)."""
    tlen = int.from_bytes(body[:2], "big")
    topic = body[2 : 2 + tlen].decode(errors="replace")
    pos = 2 + tlen
    qos = (flags >> 1) & 3
    pid = None
    if qos:
        pid = int.from_bytes(body[pos : pos + 2], "big")
        pos += 2
    return topic, body[pos:], pid


def device_from_topic(topic: str) -> str | None:
    """`org/<org>/evt/device/<deviceId>/<kind>` -> deviceId."""
    parts = topic.split("/")
    if len(parts) >= 5 and parts[0] == "org" and parts[2] == "evt" and parts[3] == "device":
        return parts[4]
    return None


class PalMqtt:
    """Keeps a connection to the portal broker and reports device events."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api: PalApi,
        on_event: Callable[[str], None],
        on_state: Callable[[bool], None],
    ) -> None:
        self._session = session
        self._api = api
        self._on_event = on_event
        self._on_state = on_state
        self.connected = False

    def _set_connected(self, value: bool) -> None:
        if value != self.connected:
            self.connected = value
            self._on_state(value)

    async def async_run(self) -> None:
        """Connect, listen, reconnect with back-off. Runs until cancelled."""
        delay = 5.0
        while True:
            try:
                await self._run_once()
                delay = 5.0  # clean end (token about to expire): reconnect soon
            except asyncio.CancelledError:
                self._set_connected(False)
                raise
            except (MqttError, PalApiError, aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
                _LOGGER.debug("PAL MQTT: %s", err)
            except Exception:  # noqa: BLE001 - never let the task die silently
                _LOGGER.exception("PAL MQTT: unexpected error")
            self._set_connected(False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300.0)

    async def _run_once(self) -> None:
        token, org_id, exp = await self._api.async_get_mqtt_credentials()
        if not org_id:
            raise MqttError("no organisation id from login")
        topic = f"org/{org_id}/#"
        client_id = "ha_pal_es_" + os.urandom(4).hex()
        # Reconnect shortly before the token expires, so the next login is fresh.
        lifetime = max(60.0, (exp - time.time() - 120) if exp else 6 * 3600.0)

        async with self._session.ws_connect(
            MQTT_URL,
            protocols=("mqtt",),
            headers={"Origin": MQTT_ORIGIN},
            heartbeat=None,
        ) as ws:
            await ws.send_bytes(build_connect(client_id, MQTT_USERNAME, token, MQTT_KEEPALIVE))
            buf = bytearray()
            started = time.monotonic()
            last_rx = started
            subscribed = False

            while True:
                if time.monotonic() - started > lifetime:
                    return
                try:
                    msg = await ws.receive(timeout=MQTT_KEEPALIVE * 0.7)
                except asyncio.TimeoutError:
                    if time.monotonic() - last_rx > MQTT_KEEPALIVE * 2:
                        raise MqttError("keep-alive timeout") from None
                    await ws.send_bytes(build_packet(PINGREQ << 4))
                    continue
                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                                aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise MqttError("connection closed")
                if msg.type != aiohttp.WSMsgType.BINARY:
                    continue
                last_rx = time.monotonic()
                buf += msg.data
                for ptype, flags, body in pop_packets(buf):
                    if ptype == CONNACK:
                        if len(body) < 2 or body[1] != 0:
                            raise MqttError(f"broker refused the connection (code {body[1:2].hex()})")
                        await ws.send_bytes(build_subscribe(1, topic))
                    elif ptype == SUBACK:
                        if body[2:3] == b"\x80":
                            raise MqttError(f"broker denied subscription to {topic}")
                        subscribed = True
                        _LOGGER.debug("PAL MQTT: subscribed to %s", topic)
                        self._set_connected(True)
                    elif ptype == PUBLISH and subscribed:
                        ev_topic, _payload, pid = parse_publish(flags, body)
                        if pid is not None:
                            await ws.send_bytes(build_packet(PUBACK << 4, pid.to_bytes(2, "big")))
                        dev = device_from_topic(ev_topic)
                        if dev:
                            self._on_event(dev)
