# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bounded read-only quota RPC through Codex's existing daemon proxy.

The proxy carries a WebSocket byte stream over its pipes, not newline JSON.
This client never starts an app server, opens a thread, or submits a turn.
"""

import base64
import hashlib
import json
import os
import selectors
import struct
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import cast

from agent_while_true.version import __version__

_TIMEOUT = 5.0
_MAX_MESSAGE = 256 * 1024
_MAX_TOTAL = 512 * 1024
_MAX_FRAMES = 64
_MAX_HEADERS = 8192
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class CodexRPCError(Exception):
    """The daemon did not provide a complete, bounded quota response."""


class _Connection:
    def __init__(self, child: subprocess.Popen[bytes], deadline: float) -> None:
        assert child.stdin is not None
        assert child.stdout is not None
        self.input_fd = child.stdin.fileno()
        self.output_fd = child.stdout.fileno()
        os.set_blocking(self.input_fd, False)
        os.set_blocking(self.output_fd, False)
        self.deadline = deadline
        self.buffer = bytearray()
        self.total = 0
        self.frames = 0

    def _ready(self, fd: int, event: int) -> None:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CodexRPCError("daemon-timeout")
        with selectors.DefaultSelector() as selector:
            selector.register(fd, event)
            if not selector.select(remaining):
                raise CodexRPCError("daemon-timeout")

    def write(self, data: bytes) -> None:
        while data:
            self._ready(self.input_fd, selectors.EVENT_WRITE)
            try:
                written = os.write(self.input_fd, data)
            except BlockingIOError:
                continue
            if written == 0:
                raise CodexRPCError("daemon-closed")
            data = data[written:]

    def _read(self) -> None:
        self._ready(self.output_fd, selectors.EVENT_READ)
        try:
            data = os.read(self.output_fd, min(8192, _MAX_TOTAL - self.total + 1))
        except BlockingIOError:
            return
        if not data:
            raise CodexRPCError("daemon-closed")
        self.total += len(data)
        if self.total > _MAX_TOTAL:
            raise CodexRPCError("daemon-response-too-large")
        self.buffer.extend(data)

    def take(self, count: int) -> bytes:
        while len(self.buffer) < count:
            self._read()
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        self.write(
            (
                "GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        while b"\r\n\r\n" not in self.buffer:
            if len(self.buffer) > _MAX_HEADERS:
                raise CodexRPCError("daemon-invalid-handshake")
            self._read()
        end = self.buffer.index(b"\r\n\r\n")
        if end > _MAX_HEADERS:
            raise CodexRPCError("daemon-invalid-handshake")
        rows = self.take(end + 4).decode("ascii").split("\r\n")
        if rows[0].split(" ", 2)[:2] != ["HTTP/1.1", "101"]:
            raise CodexRPCError("daemon-invalid-handshake")
        headers: dict[str, str] = {}
        for row in rows[1:-2]:
            name, separator, value = row.partition(":")
            name = name.lower()
            if not separator or name in headers:
                raise CodexRPCError("daemon-invalid-handshake")
            headers[name] = value.strip()
        expected = base64.b64encode(
            hashlib.sha1((key + _GUID).encode("ascii"), usedforsecurity=False).digest()
        ).decode("ascii")
        if (
            headers.get("sec-websocket-accept") != expected
            or headers.get("upgrade", "").lower() != "websocket"
            or "upgrade"
            not in {token.strip().lower() for token in headers.get("connection", "").split(",")}
        ):
            raise CodexRPCError("daemon-invalid-handshake")

    def send(self, payload: dict[str, object]) -> None:
        self._frame(1, json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    def _frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        size = len(payload)
        header = bytes([0x80 | opcode])
        if size < 126:
            header += bytes([0x80 | size])
        else:
            header += bytes([0x80 | 126]) + struct.pack("!H", size)
        self.write(header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload)))

    def response(self, request_id: int) -> dict[str, object]:
        while True:
            first, second = self.take(2)
            self.frames += 1
            if self.frames > _MAX_FRAMES or first not in (0x81, 0x88, 0x89, 0x8A) or second & 0x80:
                raise CodexRPCError("daemon-invalid-frame")
            size = second & 0x7F
            if size == 126:
                size = struct.unpack("!H", self.take(2))[0]
                if size < 126:
                    raise CodexRPCError("daemon-invalid-frame")
            elif size == 127:
                size = struct.unpack("!Q", self.take(8))[0]
                if size < 65536:
                    raise CodexRPCError("daemon-invalid-frame")
            opcode = first & 0x0F
            if size > _MAX_MESSAGE or (opcode != 1 and size > 125):
                raise CodexRPCError("daemon-response-too-large")
            payload = self.take(size)
            if opcode == 8:
                raise CodexRPCError("daemon-closed")
            if opcode == 9:
                self._frame(10, payload)
                continue
            if opcode == 10:
                continue
            message = json.loads(payload.decode("utf-8"))
            if not isinstance(message, dict):
                raise CodexRPCError("daemon-invalid-response")
            if "id" not in message and isinstance(message.get("method"), str):
                continue
            if type(message.get("id")) is not int or message["id"] != request_id:
                raise CodexRPCError("daemon-invalid-response")
            if "error" in message or not isinstance(message.get("result"), dict):
                raise CodexRPCError("daemon-rpc-failed")
            return cast(dict[str, object], message["result"])


def read_daemon_quota(home: Path) -> dict[str, object]:
    """Read account/rateLimits/read without modifying daemon/provider state.

    Only the newly spawned proxy is terminated. RPC payloads and exceptions
    from the provider are never included in errors or logs.
    """
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(home)
    child: subprocess.Popen[bytes] | None = None
    try:
        deadline = time.monotonic() + _TIMEOUT
        child = subprocess.Popen(
            ["codex", "app-server", "proxy"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            bufsize=0,
        )
        connection = _Connection(child, deadline)
        connection.handshake()
        connection.send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "agent_while_true", "version": __version__},
                    "capabilities": {"explicitGatewayOauth": True},
                },
            }
        )
        connection.response(1)
        connection.send({"method": "initialized"})
        connection.send({"id": 2, "method": "account/rateLimits/read", "params": None})
        return connection.response(2)
    except OSError, ValueError, UnicodeError, RecursionError, CodexRPCError:
        raise CodexRPCError("daemon-quota-unavailable") from None
    finally:
        if child is not None:
            if child.poll() is None:
                with suppress(ProcessLookupError):
                    child.terminate()
            try:
                child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    child.kill()
                child.wait(timeout=0.2)
            if child.stdin is not None:
                child.stdin.close()
            if child.stdout is not None:
                child.stdout.close()
