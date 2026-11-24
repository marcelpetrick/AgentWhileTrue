# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The minimal session-bus client, against an in-process fake bus daemon."""

import shutil
import socket
import struct
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from agent_while_true.terminal import dbus
from agent_while_true.terminal.dbus import BusCallError, BusError, SessionBus, session_bus_path

Message = tuple[int, int, dict[int, object], bytes, bool]


def _variant(writer: dbus._Writer, kind: str, value: object) -> None:
    writer.signature(kind)
    if kind == "u":
        writer.fixed("u", int(value))  # type: ignore[call-overload]
    else:
        writer.value(kind, value)


def _body(signature: str, values: tuple[object, ...]) -> bytes:
    writer = dbus._Writer()
    for kind, value in zip(dbus._split_signature(signature), values, strict=True):
        if kind == "as":
            items = dbus._Writer()
            for item in value:  # type: ignore[attr-defined]
                items.string(item)
            writer.fixed("u", len(items.data))
            writer.data.extend(items.data)
        elif kind == "u":
            writer.fixed("u", int(value))  # type: ignore[call-overload]
        else:
            writer.value(kind, value)
    return bytes(writer.data)


def message(
    kind: int,
    *,
    reply_to: int = 0,
    signature: str = "",
    values: tuple[object, ...] = (),
    error: str = "",
    big_endian: bool = False,
    body: bytes | None = None,
) -> bytes:
    """Build one bus message the way a daemon would send it."""
    payload = _body(signature, values) if body is None else body
    fields = dbus._Writer()
    entries: list[tuple[int, str, object]] = []
    if reply_to:
        entries.append((dbus._REPLY_SERIAL, "u", reply_to))
    if signature:
        entries.append((dbus._SIGNATURE, "g", signature))
    if error:
        entries.append((dbus._ERROR_NAME, "s", error))
    for code, field_kind, value in entries:
        fields.pad(8)
        fields.data.append(code)
        _variant(fields, field_kind, value)
    header = dbus._Writer()
    header.data.extend(b"l" + bytes([kind, 0, 1]))
    header.fixed("u", len(payload))
    header.fixed("u", 7)
    header.fixed("u", len(fields.data))
    header.data.extend(fields.data)
    header.pad(8)
    raw = bytes(header.data) + payload
    if big_endian:
        # Only fixed header ints and the u32-sized pieces used here differ.
        raw = _to_big_endian(raw, len(fields.data), signature, payload)
    return raw


def _to_big_endian(raw: bytes, fields_size: int, signature: str, payload: bytes) -> bytes:
    assert signature == "i"
    head = b"B" + raw[1:4] + struct.pack(">III", len(payload), 7, fields_size)
    fields = bytearray(raw[16 : len(raw) - len(payload)])
    # The reply-serial variant's u32 sits at offset 4 of the first field struct.
    fields[4:8] = struct.pack(">I", struct.unpack("<I", fields[4:8])[0])
    return head + bytes(fields) + struct.pack(">i", struct.unpack("<i", payload)[0])


class FakeDaemon:
    """Accept connections, authenticate, and answer each call with ``respond``."""

    def __init__(self, path: Path, respond: Callable[[Message, int], list[bytes]]) -> None:
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen(4)
        self.respond = respond
        self.auth_reply = b"OK 1234\r\n"
        self.calls: list[tuple[str, str, str, list[object]]] = []
        self.connections = 0
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self.server.accept()
            except OSError:
                return
            self.connections += 1
            with connection:
                self._session(connection)

    def _session(self, connection: socket.socket) -> None:
        data = b""
        while not data.endswith(b"\r\n"):
            data += connection.recv(1)
        assert data.startswith(b"\0AUTH EXTERNAL ")
        connection.sendall(self.auth_reply)
        if not self.auth_reply.startswith(b"OK"):
            return
        assert connection.recv(7) == b"BEGIN\r\n"
        reader = SessionBus(path="unused")
        reader._sock = connection
        try:
            while True:
                incoming = reader._read_message()
                _, serial, fields, body, little = incoming
                values = [
                    dbus._Reader(body, little).value(code)
                    for code in dbus._split_signature(str(fields.get(dbus._SIGNATURE, "")))
                ]
                self.calls.append(
                    (
                        str(fields[dbus._DESTINATION]),
                        str(fields[dbus._PATH]),
                        str(fields[dbus._MEMBER]),
                        values,
                    )
                )
                for reply in self.respond(incoming, serial):
                    connection.sendall(reply)
        except BusError, OSError:
            return

    def close(self) -> None:
        self.server.close()


def _standard(incoming: Message, serial: int) -> list[bytes]:
    member = incoming[2][dbus._MEMBER]
    if member == "Hello":
        return [
            message(dbus._METHOD_RETURN, reply_to=serial, signature="s", values=(":1.9",)),
            message(4, signature="s", values=(":1.9",)),  # NameAcquired signal
        ]
    if member == "ListNames":
        return [
            message(4, signature="s", values=("noise",)),
            message(
                dbus._METHOD_RETURN,
                reply_to=serial,
                signature="as",
                values=(["org.freedesktop.DBus", "org.kde.konsole-7"],),
            ),
        ]
    if member == "processId":
        return [message(dbus._METHOD_RETURN, reply_to=serial, signature="i", values=(4242,))]
    return [message(dbus._ERROR, reply_to=serial, error="org.freedesktop.DBus.Error.UnknownObject")]


@pytest.fixture
def socket_dir() -> Iterator[Path]:
    # AF_UNIX paths are limited to 107 bytes; pytest's tmp_path can exceed it.
    short = Path(tempfile.mkdtemp(prefix="awtbus", dir="/tmp"))
    yield short
    shutil.rmtree(short, ignore_errors=True)


def _daemon(path: Path, respond=_standard) -> FakeDaemon:
    return FakeDaemon(path / "bus", respond)


def test_a_call_authenticates_skips_signals_and_decodes_the_reply(socket_dir: Path) -> None:
    daemon = _daemon(socket_dir)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        signature, values = bus.call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames"
        )
        assert (signature, values) == ("as", [["org.freedesktop.DBus", "org.kde.konsole-7"]])
        assert bus.call("org.kde.konsole-7", "/Sessions/1", "org.kde.konsole.Session", "processId")
        assert daemon.connections == 1  # one persistent connection
        assert [call[2] for call in daemon.calls] == ["Hello", "ListNames", "processId"]
    finally:
        bus.close()
        daemon.close()


def test_arguments_are_marshalled_with_their_signature(socket_dir: Path) -> None:
    daemon = _daemon(socket_dir)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        with pytest.raises(BusCallError, match="UnknownObject"):
            bus.call("svc", "/Sessions/1", "org.kde.konsole.Session", "title", "i", (1,))
        with pytest.raises(BusCallError):
            bus.call("svc", "/Sessions/1", "iface", "getAllDisplayedTextList", "b", (True,))
        with pytest.raises(BusCallError):
            bus.call("svc", "/a", "iface", "m", "s", ("text",))
        # An error reply leaves the connection usable.
        assert daemon.connections == 1
        assert daemon.calls[1][3] == [1]
        assert daemon.calls[2][3] == [True]
        assert daemon.calls[3][3] == ["text"]
    finally:
        bus.close()
        daemon.close()


@pytest.mark.parametrize(
    ("signature", "args", "reason"),
    [
        ("s", ("nul\0inside",), "NUL"),
        ("x", (1,), "cannot marshal"),
        ("i", (True,), "cannot marshal"),
        ("ii", (1,), "argument count"),
        ("(i", (1,), "unterminated"),
        ("a", ((),), "truncated signature"),
        ("h", (1,), "unsupported"),
    ],
)
def test_unsupported_arguments_are_refused_before_sending(
    socket_dir: Path, signature: str, args: tuple[object, ...], reason: str
) -> None:
    daemon = _daemon(socket_dir)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        with pytest.raises(BusError, match=reason):
            bus.call("svc", "/p", "iface", "m", signature, args)
    finally:
        bus.close()
        daemon.close()


def test_a_rejected_authentication_is_a_transport_error(socket_dir: Path) -> None:
    daemon = _daemon(socket_dir)
    daemon.auth_reply = b"REJECTED EXTERNAL\r\n"
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        with pytest.raises(BusError, match="rejected"):
            bus.call("svc", "/p", "iface", "m")
    finally:
        daemon.close()


def test_a_refused_hello_is_a_transport_error(socket_dir: Path) -> None:
    def refuse(incoming: Message, serial: int) -> list[bytes]:
        return [message(dbus._ERROR, reply_to=serial, error="org.freedesktop.DBus.Error.Denied")]

    daemon = _daemon(socket_dir, refuse)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        with pytest.raises(BusError, match="Hello"):
            bus.call("svc", "/p", "iface", "m")
    finally:
        daemon.close()


def test_a_dropped_connection_is_reopened_on_the_next_call(socket_dir: Path) -> None:
    replies = iter([True, False, True, True])

    def flaky(incoming: Message, serial: int) -> list[bytes]:
        if incoming[2][dbus._MEMBER] == "Hello":
            return _standard(incoming, serial)
        if next(replies):
            return [message(dbus._METHOD_RETURN, reply_to=serial, signature="i", values=(1,))]
        raise OSError("hang up")

    daemon = _daemon(socket_dir, flaky)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        assert bus.call("svc", "/p", "iface", "m") == ("i", [1])
        with pytest.raises(BusError, match="closed"):
            bus.call("svc", "/p", "iface", "m")
        assert bus._sock is None
        assert bus.call("svc", "/p", "iface", "m") == ("i", [1])
        assert daemon.connections == 2
    finally:
        bus.close()
        daemon.close()


def test_a_big_endian_reply_is_decoded(socket_dir: Path) -> None:
    def big(incoming: Message, serial: int) -> list[bytes]:
        if incoming[2][dbus._MEMBER] == "Hello":
            return _standard(incoming, serial)
        reply = message(
            dbus._METHOD_RETURN, reply_to=serial, signature="i", values=(-5,), big_endian=True
        )
        return [reply]

    daemon = _daemon(socket_dir, big)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        assert bus.call("svc", "/p", "iface", "m") == ("i", [-5])
    finally:
        bus.close()
        daemon.close()


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"x" + bytes(15), "version 1"),
        (b"l\x02\x00\x01" + struct.pack("<III", dbus.MAX_REPLY_BYTES + 1, 1, 0), "too large"),
    ],
)
def test_malformed_or_oversized_messages_close_the_connection(
    socket_dir: Path, raw: bytes, reason: str
) -> None:
    def broken(incoming: Message, serial: int) -> list[bytes]:
        if incoming[2][dbus._MEMBER] == "Hello":
            return _standard(incoming, serial)
        return [raw]

    daemon = _daemon(socket_dir, broken)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        with pytest.raises(BusError, match=reason):
            bus.call("svc", "/p", "iface", "m")
        assert bus._sock is None
    finally:
        daemon.close()


def test_a_reply_body_that_disagrees_with_its_signature_is_refused(socket_dir: Path) -> None:
    def lying(incoming: Message, serial: int) -> list[bytes]:
        if incoming[2][dbus._MEMBER] == "Hello":
            return _standard(incoming, serial)
        if incoming[2][dbus._MEMBER] == "short":
            body = struct.pack("<I", 50) + b"abc"
            return [message(2, reply_to=serial, signature="s", values=(), body=body)]
        body = struct.pack("<i", 1) + b"extra"
        return [message(2, reply_to=serial, signature="i", values=(), body=body)]

    daemon = _daemon(socket_dir, lying)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        with pytest.raises(BusError, match="trailing"):
            bus.call("svc", "/p", "iface", "long")
        with pytest.raises(BusError, match="truncated"):
            bus.call("svc", "/p", "iface", "short")
    finally:
        daemon.close()


def test_no_reply_among_many_signals_is_an_error(socket_dir: Path) -> None:
    def chatty(incoming: Message, serial: int) -> list[bytes]:
        if incoming[2][dbus._MEMBER] == "Hello":
            return _standard(incoming, serial)
        return [message(4, signature="s", values=("noise",))] * (dbus._MAX_SKIPPED_MESSAGES + 1)

    daemon = _daemon(socket_dir, chatty)
    bus = SessionBus(path=str(socket_dir / "bus"), timeout=2)
    try:
        with pytest.raises(BusError, match="no reply"):
            bus.call("svc", "/p", "iface", "m")
    finally:
        daemon.close()


def test_an_unreachable_bus_is_a_transport_error(socket_dir: Path) -> None:
    bus = SessionBus(path=str(socket_dir / "missing"), timeout=1)
    with pytest.raises(BusError):
        bus.call("svc", "/p", "iface", "m")
    bus.close()  # closing twice is harmless


def test_the_reader_decodes_every_supported_type() -> None:
    writer = dbus._Writer()
    writer.fixed("y", 7)
    writer.fixed("b", 1)
    writer.fixed("i", -3)
    writer.string("text")
    writer.signature("ai")
    array = dbus._Writer()
    for value in (1, 2):
        array.fixed("i", value)
    writer.fixed("u", len(array.data))
    writer.data.extend(array.data)
    writer.pad(8)
    writer.fixed("i", 9)
    writer.string("in-struct")
    writer.signature("i")
    writer.fixed("i", 11)
    reader = dbus._Reader(bytes(writer.data), little=True)
    values = [reader.value(code) for code in dbus._split_signature("ybisgai(is)v")]
    assert values == [7, True, -3, "text", "ai", [1, 2], (9, "in-struct"), 11]


@pytest.mark.parametrize(
    ("data", "signature", "reason"),
    [
        (struct.pack("<I", 1) + b"ab", "s", "unterminated string"),
        (b"\x01ab", "g", "unterminated signature"),
        (b"\x02ii\x00", "v", "exactly one"),
        (struct.pack("<I", 6) + struct.pack("<i", 1), "ai", "truncated array"),
        (struct.pack("<I", 2) + struct.pack("<i", 1), "ai", "array length"),
        (b"", "i", "truncated"),
        (b"\x00" * 3, "x", "truncated"),
    ],
)
def test_the_reader_refuses_malformed_values(data: bytes, signature: str, reason: str) -> None:
    with pytest.raises(BusError, match=reason):
        dbus._Reader(data, little=True).value(signature)


def test_a_misaligned_read_past_the_end_is_truncated() -> None:
    reader = dbus._Reader(b"\x01", little=True)
    reader.offset = 1
    with pytest.raises(BusError, match="truncated"):
        reader.align(8)


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("unix:path=/run/user/1000/bus", "/run/user/1000/bus"),
        ("unix:abstract=/tmp/dbus-x,guid=1", "\0/tmp/dbus-x"),
        ("tcp:host=localhost,port=1;unix:path=/b", "/b"),
        ("tcp:host=localhost,port=1", None),
        ("unix:guid=1", None),
        ("", None),
        (None, None),
    ],
)
def test_only_local_unix_bus_addresses_are_used(address: str | None, expected: str | None) -> None:
    assert session_bus_path(address) == expected


def test_the_environment_names_the_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/bus")
    bus = SessionBus.from_environment(timeout=3)
    assert bus is not None
    assert (bus.path, bus.timeout) == ("/run/bus", 3)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS")
    assert SessionBus.from_environment() is None
