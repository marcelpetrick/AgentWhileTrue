# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only daemon transport tests; no installed Codex process is used."""

import base64
import hashlib
import json
import os
import struct
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_while_true import codex_rpc as rpc


def frame(payload: bytes, first: int = 0x81) -> bytes:
    size = len(payload)
    if size < 126:
        return bytes([first, size]) + payload
    if size < 65536:
        return bytes([first, 126]) + struct.pack("!H", size) + payload
    return bytes([first, 127]) + struct.pack("!Q", size) + payload


class Proxy:
    def __init__(self, output: bytes) -> None:
        self.input_reader, writer = os.pipe()
        reader, self.output_writer = os.pipe()
        self.stdin = os.fdopen(writer, "wb", buffering=0)
        self.stdout = os.fdopen(reader, "rb", buffering=0)
        os.write(self.output_writer, output)
        os.close(self.output_writer)
        self.terminated = False
        self.killed = False
        self.stubborn = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        if self.stubborn and not self.killed:
            raise subprocess.TimeoutExpired("private", timeout)
        return 0

    def kill(self):
        self.killed = True


def handshake() -> bytes:
    key = base64.b64encode(b"x" * 16).decode()
    accept = base64.b64encode(
        hashlib.sha1((key + rpc._GUID).encode(), usedforsecurity=False).digest()
    ).decode()
    return (
        "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"
    ).encode()


@pytest.fixture
def proxy_factory(monkeypatch):
    proxies = []
    monkeypatch.setattr(rpc.os, "urandom", lambda count: b"x" * count)

    def make(output):
        proxy = Proxy(output)
        proxies.append(proxy)

        def popen(command, **kwargs):
            assert command == ["codex", "app-server", "proxy"]
            assert kwargs["env"]["CODEX_HOME"] == "/fixture/profile"
            assert kwargs["stderr"] == subprocess.DEVNULL
            return proxy

        monkeypatch.setattr(rpc.subprocess, "Popen", popen)
        return proxy

    yield make
    for proxy in proxies:
        proxy.stdin.close()
        proxy.stdout.close()
        os.close(proxy.input_reader)


def test_complete_handshake_and_masked_read_only_rpc(proxy_factory):
    result = {"accountId": "redacted", "ordinaryUsageAllowed": True}
    proxy = proxy_factory(
        handshake()
        + frame(b'{"id":1,"result":{}}')
        + frame(b'{"method":"status","params":{}}')
        + frame(json.dumps({"id": 2, "result": result}).encode())
    )
    assert rpc.read_daemon_quota(Path("/fixture/profile")) == result
    assert proxy.terminated
    outgoing = os.read(proxy.input_reader, 8192)
    header, outgoing = outgoing.split(b"\r\n\r\n", 1)
    assert b"GET / HTTP/1.1" in header
    messages = []
    while outgoing:
        assert outgoing[0] == 0x81
        assert outgoing[1] & 0x80
        size = outgoing[1] & 0x7F
        offset = 2
        if size == 126:
            size = struct.unpack("!H", outgoing[2:4])[0]
            offset = 4
        mask = outgoing[offset : offset + 4]
        payload = outgoing[offset + 4 : offset + 4 + size]
        messages.append(json.loads(bytes(value ^ mask[i % 4] for i, value in enumerate(payload))))
        outgoing = outgoing[offset + 4 + size :]
    assert [message["method"] for message in messages] == [
        "initialize",
        "initialized",
        "account/rateLimits/read",
    ]
    assert messages[0]["params"]["capabilities"] == {"explicitGatewayOauth": True}
    assert messages[2]["params"] is None


@pytest.mark.parametrize(
    "output",
    [
        b"HTTP/1.1 403 Forbidden\r\n\r\n",
        handshake().replace(b"Upgrade: websocket", b"Upgrade: private"),
        handshake().replace(b"Connection: Upgrade", b"Connection: close"),
        handshake().replace(b"Sec-WebSocket-Accept:", b"Private:"),
        handshake().replace(b"Connection: Upgrade", b"Connection: Upgrade\r\nConnection: Upgrade"),
        handshake().replace(b"Connection: Upgrade", b"broken"),
        b"\xff\r\n\r\n",
        b"partial",
        handshake() + frame(b"private invalid JSON"),
        handshake() + frame(b'{"id":1,"error":{"message":"private"}}'),
        handshake() + frame(b'{"id":2,"result":{}}'),
        handshake() + frame(b'{"id":true,"result":{}}'),
        handshake() + frame(b'{"id":1,"result":[]}'),
        handshake() + frame(b"[]"),
        handshake() + frame(b"{}"),
        handshake() + frame(b"\xff"),
    ],
)
def test_failure_is_generic_and_child_reaped(proxy_factory, output):
    proxy = proxy_factory(output)
    with pytest.raises(rpc.CodexRPCError, match=r"^daemon-quota-unavailable$") as caught:
        rpc.read_daemon_quota(Path("/fixture/profile"))
    assert caught.value.__cause__ is None
    assert proxy.terminated
    assert proxy.stdin.closed
    assert proxy.stdout.closed


def test_stubborn_child_killed(proxy_factory):
    proxy = proxy_factory(b"")
    proxy.stubborn = True
    with pytest.raises(rpc.CodexRPCError):
        rpc.read_daemon_quota(Path("/fixture/profile"))
    assert proxy.killed


def connection_with_wire(wire: bytes):
    connection = object.__new__(rpc._Connection)
    connection.buffer = bytearray(wire)
    connection.frames = 0
    connection.total = 0
    connection.deadline = time.monotonic() + 5
    return connection


@pytest.mark.parametrize(
    "wire",
    [
        b"\x01\x00",
        b"\xc1\x00",
        b"\x82\x00",
        b"\x81\x80",
        b"\x81\x7e\x00\x01",
        b"\x81\x7f" + struct.pack("!Q", 65535),
        b"\x81\x7f" + struct.pack("!Q", rpc._MAX_MESSAGE + 1),
        b"\x89\x7e\x00\x7e",
        b"\x88\x00",
    ],
)
def test_invalid_frames_fail_closed(wire):
    with pytest.raises(rpc.CodexRPCError):
        connection_with_wire(wire).response(1)


@pytest.mark.parametrize("size", [126, 65536])
def test_extended_text_frames(size):
    payload = json.dumps({"id": 1, "result": {"padding": "x" * size}}).encode()
    assert len(connection_with_wire(frame(payload)).response(1)["padding"]) == size


def test_ping_pong_and_event_bounds(monkeypatch):
    connection = connection_with_wire(
        frame(b"ping", 0x89) + frame(b"", 0x8A) + frame(b'{"id":1,"result":{}}')
    )
    sent = []
    monkeypatch.setattr(
        connection, "_frame", lambda opcode, payload: sent.append((opcode, payload))
    )
    assert connection.response(1) == {}
    assert sent == [(10, b"ping")]
    with pytest.raises(rpc.CodexRPCError):
        connection_with_wire(frame(b'{"method":"event"}') * 65).response(1)


def test_timeout_before_read_and_selector_timeout(monkeypatch):
    connection = connection_with_wire(b"")
    connection.deadline = 0
    with pytest.raises(rpc.CodexRPCError, match="daemon-timeout"):
        connection._ready(0, 1)
    connection.deadline = time.monotonic() + 1
    selector = SimpleNamespace(register=lambda *args: None, select=lambda timeout: [])
    monkeypatch.setattr(rpc.selectors, "DefaultSelector", lambda: SelectorContext(selector))
    with pytest.raises(rpc.CodexRPCError, match="daemon-timeout"):
        connection._ready(0, 1)


class SelectorContext:
    def __init__(self, selector):
        self.selector = selector

    def __enter__(self):
        return self.selector

    def __exit__(self, *args):
        return False


def test_read_total_limit_and_transient_read(monkeypatch):
    connection = connection_with_wire(b"")
    connection.output_fd = 0
    monkeypatch.setattr(connection, "_ready", lambda *args: None)
    monkeypatch.setattr(rpc.os, "read", lambda *args: b"xx")
    connection.total = rpc._MAX_TOTAL - 1
    with pytest.raises(rpc.CodexRPCError, match="too-large"):
        connection._read()

    def blocked(*args):
        raise BlockingIOError

    monkeypatch.setattr(rpc.os, "read", blocked)
    connection._read()


def test_partial_writes_and_temporary_backpressure(monkeypatch):
    connection = connection_with_wire(b"")
    connection.input_fd = 0
    monkeypatch.setattr(connection, "_ready", lambda *args: None)
    writes = iter([BlockingIOError(), 1, 2])

    def write(*args):
        value = next(writes)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(rpc.os, "write", write)
    connection.write(b"abc")
    monkeypatch.setattr(rpc.os, "write", lambda *args: 0)
    with pytest.raises(rpc.CodexRPCError, match="daemon-closed"):
        connection.write(b"x")


def test_missing_proxy_is_generic(monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("private path")

    monkeypatch.setattr(rpc.subprocess, "Popen", unavailable)
    with pytest.raises(rpc.CodexRPCError, match=r"^daemon-quota-unavailable$"):
        rpc.read_daemon_quota(Path("/fixture/profile"))


@pytest.mark.parametrize("complete", [False, True])
def test_oversized_handshake_headers(monkeypatch, complete):
    connection = connection_with_wire(b"x" * (rpc._MAX_HEADERS + 1))
    monkeypatch.setattr(connection, "write", lambda data: None)
    if complete:
        connection.buffer.extend(b"\r\n\r\n")
    with pytest.raises(rpc.CodexRPCError, match="invalid-handshake"):
        connection.handshake()


def test_take_reads_until_complete(monkeypatch):
    connection = connection_with_wire(b"a")
    monkeypatch.setattr(connection, "_read", lambda: connection.buffer.extend(b"b"))
    assert connection.take(3) == b"abb"
    assert not connection.buffer


def test_already_exited_child_and_terminate_race(proxy_factory, monkeypatch):
    proxy = proxy_factory(b"")
    monkeypatch.setattr(proxy, "poll", lambda: 0)
    with pytest.raises(rpc.CodexRPCError):
        rpc.read_daemon_quota(Path("/fixture/profile"))
    assert not proxy.terminated
    proxy = proxy_factory(b"")

    def gone():
        raise ProcessLookupError

    monkeypatch.setattr(proxy, "terminate", gone)
    monkeypatch.setattr(proxy, "kill", gone)
    calls = []

    def wait(timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired("private", timeout)
        return 0

    monkeypatch.setattr(proxy, "wait", wait)
    with pytest.raises(rpc.CodexRPCError):
        rpc.read_daemon_quota(Path("/fixture/profile"))
    assert len(calls) == 2
