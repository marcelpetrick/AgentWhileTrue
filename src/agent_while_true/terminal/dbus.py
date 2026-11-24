# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A minimal, read-only-sized D-Bus client on one persistent session-bus socket.

Every Konsole read used to launch ``qdbus6``: about 4 ms of CPU per call, and a
scan of a dozen tabs makes dozens of calls every two seconds. This client
speaks just enough of the D-Bus wire protocol (EXTERNAL authentication, method
calls, replies and errors) for the Konsole adapter's reads. It marshals only
the argument types those reads use and decodes only basic types and arrays of
them. Anything else - an unexpected type, a malformed or oversized message, a
timeout - is a :class:`BusError`. The connection is then closed, and the caller
falls back to ``qdbus``; nothing is guessed from a partial reply.

Standard library only; no D-Bus binding is a dependency.
"""

import os
import socket
import struct
import urllib.parse
from dataclasses import dataclass, field

#: Wire-protocol message types.
_METHOD_CALL = 1
_METHOD_RETURN = 2
_ERROR = 3

#: Header field codes.
_PATH, _INTERFACE, _MEMBER, _ERROR_NAME, _REPLY_SERIAL, _DESTINATION, _SENDER, _SIGNATURE = (
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
)

#: The specification's own limit for one message.
_MAX_MESSAGE_BYTES = 128 * 1024 * 1024
#: Far above any Konsole reply (a window of text is a few hundred kB at most);
#: a larger one is not something this client should buffer.
MAX_REPLY_BYTES = 16 * 1024 * 1024
#: Unrelated messages (signals) tolerated while waiting for one reply.
_MAX_SKIPPED_MESSAGES = 256

_ALIGN = {"y": 1, "b": 4, "n": 2, "q": 2, "i": 4, "u": 4, "x": 8, "t": 8, "d": 8}
_ALIGN |= {"s": 4, "o": 4, "g": 1, "a": 4, "(": 8, "v": 1}
_FIXED = {"y": "B", "b": "I", "n": "h", "q": "H", "i": "i", "u": "I", "x": "q", "t": "Q", "d": "d"}


class BusError(Exception):
    """The bus could not be reached or a message could not be exchanged."""


class BusCallError(Exception):
    """The callee answered with a D-Bus error (for example: no such object)."""


def session_bus_path(address: str | None) -> str | None:
    """The socket path of a ``unix:path=`` or ``unix:abstract=`` address.

    Only plain local Unix transports qualify; TCP, ``unixexec`` and launchd
    addresses are not supported, so the caller keeps using ``qdbus``.
    """
    if not address:
        return None
    for candidate in address.split(";"):
        transport, _, options = candidate.partition(":")
        if transport != "unix":
            continue
        pairs = dict(item.partition("=")[::2] for item in options.split(",") if item)
        # Address values may percent-escape any byte.
        if pairs.get("path"):
            return urllib.parse.unquote(pairs["path"])
        if pairs.get("abstract"):
            return "\0" + urllib.parse.unquote(pairs["abstract"])
    return None


class _Writer:
    def __init__(self) -> None:
        self.data = bytearray()

    def pad(self, alignment: int) -> None:
        self.data.extend(b"\0" * (-len(self.data) % alignment))

    def fixed(self, code: str, value: int) -> None:
        self.pad(_ALIGN[code])
        self.data.extend(struct.pack("<" + _FIXED[code], value))

    def string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if b"\0" in encoded:
            raise BusError("a D-Bus string cannot contain NUL")
        self.fixed("u", len(encoded))
        self.data.extend(encoded + b"\0")

    def signature(self, value: str) -> None:
        encoded = value.encode("ascii")
        self.data.extend(bytes([len(encoded)]) + encoded + b"\0")

    def value(self, code: str, value: object) -> None:
        if code in {"s", "o"} and isinstance(value, str):
            self.string(value)
        elif code == "g" and isinstance(value, str):
            self.signature(value)
        elif code == "b" and isinstance(value, bool):
            self.fixed("b", int(value))
        elif code == "i" and isinstance(value, int) and not isinstance(value, bool):
            self.fixed("i", value)
        else:
            raise BusError(f"cannot marshal {code!r}")


def _split_signature(signature: str) -> list[str]:
    """Split a signature into complete types (``as``, ``s``, ``(is)`` ...)."""
    types: list[str] = []
    index = 0
    while index < len(signature):
        end = _complete_type_end(signature, index)
        types.append(signature[index:end])
        index = end
    return types


def _complete_type_end(signature: str, index: int) -> int:
    if index >= len(signature):
        raise BusError("truncated signature")
    code = signature[index]
    if code == "a":
        return _complete_type_end(signature, index + 1)
    if code == "(":
        index += 1
        while index < len(signature) and signature[index] != ")":
            index = _complete_type_end(signature, index)
        if index >= len(signature):
            raise BusError("unterminated struct signature")
        return index + 1
    if code in _ALIGN:
        return index + 1
    raise BusError(f"unsupported type {code!r}")


class _Reader:
    def __init__(self, data: bytes, little: bool) -> None:
        self.data = data
        self.offset = 0
        self.order = "<" if little else ">"

    def align(self, alignment: int) -> None:
        self.offset += -self.offset % alignment
        if self.offset > len(self.data):
            raise BusError("truncated message")

    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            raise BusError("truncated message")
        chunk = self.data[self.offset : self.offset + size]
        self.offset += size
        return chunk

    def fixed(self, code: str) -> int | float:
        self.align(_ALIGN[code])
        fmt = self.order + _FIXED[code]
        (value,) = struct.unpack(fmt, self.take(struct.calcsize(fmt)))
        result: int | float = value
        return result

    def value(self, code: str) -> object:
        head = code[0]
        if head in _FIXED:
            raw = self.fixed(head)
            return bool(raw) if head == "b" else raw
        if head in {"s", "o"}:
            size = int(self.fixed("u"))
            text = self.take(size)
            if self.take(1) != b"\0":
                raise BusError("unterminated string")
            return text.decode("utf-8", "replace")
        if head == "g":
            size = self.take(1)[0]
            text = self.take(size)
            if self.take(1) != b"\0":
                raise BusError("unterminated signature")
            return text.decode("ascii", "replace")
        if head == "v":
            inner = str(self.value("g"))
            if len(_split_signature(inner)) != 1:
                raise BusError("a variant holds exactly one type")
            return self.value(inner)
        if head == "a":
            size = int(self.fixed("u"))
            element = code[1:]
            self.align(_ALIGN[element[0]])
            end = self.offset + size
            if end > len(self.data):
                raise BusError("truncated array")
            items = []
            while self.offset < end:
                items.append(self.value(element))
            if self.offset != end:
                raise BusError("array length mismatch")
            return items
        if head == "(":
            self.align(8)
            return tuple(self.value(part) for part in _split_signature(code[1:-1]))
        raise BusError(f"unsupported type {code!r}")  # pragma: no cover - split rejects it


@dataclass
class SessionBus:
    """One lazily opened connection; every failure closes it for a fresh retry."""

    path: str
    timeout: float = 5.0
    _sock: socket.socket | None = field(default=None, repr=False)
    _serial: int = field(default=0, repr=False)
    _buffer: bytearray = field(default_factory=bytearray, repr=False)

    @classmethod
    def from_environment(cls, timeout: float = 5.0) -> SessionBus | None:
        path = session_bus_path(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
        return cls(path=path, timeout=timeout) if path else None

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
        self._sock = None
        self._buffer.clear()

    def call(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        args: tuple[object, ...] = (),
    ) -> tuple[str, list[object]]:
        """Call one method; return the reply's signature and decoded values.

        Raises :class:`BusCallError` for a D-Bus error reply (the connection
        stays usable) and :class:`BusError` for anything else (it is closed).
        """
        try:
            if self._sock is None:
                self._connect()
            serial = self._send(destination, path, interface, member, signature, args)
            return self._await_reply(serial)
        except BusCallError:
            raise
        except (OSError, struct.error, UnicodeError, ValueError, IndexError) as exc:
            self.close()
            raise BusError(str(exc) or type(exc).__name__) from exc
        except BusError:
            self.close()
            raise

    # -- plumbing -------------------------------------------------------------

    def _connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.path)
            uid = str(os.getuid()).encode("ascii").hex()
            sock.sendall(b"\0AUTH EXTERNAL " + uid.encode("ascii") + b"\r\n")
            line = self._auth_line(sock)
            if not line.startswith(b"OK "):
                raise BusError("the bus rejected EXTERNAL authentication")
            sock.sendall(b"BEGIN\r\n")
        except BaseException:
            sock.close()
            raise
        self._sock = sock
        try:
            self._await_reply(
                self._send(
                    "org.freedesktop.DBus",
                    "/org/freedesktop/DBus",
                    "org.freedesktop.DBus",
                    "Hello",
                    "",
                    (),
                )
            )
        except BusCallError as exc:
            raise BusError(f"the bus refused Hello: {exc}") from exc

    def _auth_line(self, sock: socket.socket) -> bytes:
        data = bytearray()
        while not data.endswith(b"\r\n"):
            chunk = sock.recv(1)
            if not chunk or len(data) > 512:
                raise BusError("authentication ended early")
            data.extend(chunk)
        return bytes(data)

    def _send(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str,
        args: tuple[object, ...],
    ) -> int:
        types = _split_signature(signature)
        if len(types) != len(args):
            raise BusError("argument count does not match the signature")
        body = _Writer()
        for code, value in zip(types, args, strict=True):
            body.value(code, value)
        self._serial = self._serial % 0xFFFFFFFF + 1
        fields = [
            (_PATH, "o", path),
            (_INTERFACE, "s", interface),
            (_MEMBER, "s", member),
            (_DESTINATION, "s", destination),
        ]
        if signature:
            fields.append((_SIGNATURE, "g", signature))
        header = _Writer()
        header.data.extend(b"l" + bytes([_METHOD_CALL, 0, 1]))
        header.fixed("u", len(body.data))
        header.fixed("u", self._serial)
        array = _Writer()
        for field_code, kind, field_value in fields:
            array.pad(8)
            array.data.append(field_code)
            array.signature(kind)
            array.value(kind, field_value)
        header.fixed("u", len(array.data))
        header.pad(8)
        header.data.extend(array.data)
        header.pad(8)
        assert self._sock is not None
        self._sock.sendall(bytes(header.data) + bytes(body.data))
        return self._serial

    def _await_reply(self, serial: int) -> tuple[str, list[object]]:
        for _ in range(_MAX_SKIPPED_MESSAGES):
            kind, _, fields, body, little = self._read_message()
            if kind not in {_METHOD_RETURN, _ERROR} or fields.get(_REPLY_SERIAL) != serial:
                continue  # a signal (NameAcquired) or an unrelated message
            signature = str(fields.get(_SIGNATURE, ""))
            reader = _Reader(body, little)
            values = [reader.value(code) for code in _split_signature(signature)]
            if reader.offset != len(body):
                raise BusError("trailing bytes in the reply body")
            if kind == _ERROR:
                raise BusCallError(str(fields.get(_ERROR_NAME, "error")))
            return signature, values
        raise BusError("no reply among the messages received")

    def _read_exactly(self, size: int) -> bytes:
        assert self._sock is not None
        while len(self._buffer) < size:
            chunk = self._sock.recv(max(65536, size - len(self._buffer)))
            if not chunk:
                raise BusError("the bus closed the connection")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def _read_message(self) -> tuple[int, int, dict[int, object], bytes, bool]:
        """Read one message: its type, serial, header fields, body and byte order."""
        fixed = self._read_exactly(16)
        if fixed[0:1] not in {b"l", b"B"} or fixed[3] != 1:
            raise BusError("not a D-Bus version 1 message")
        little = fixed[0:1] == b"l"
        order = "<" if little else ">"
        body_size, serial, fields_size = struct.unpack(order + "III", fixed[4:16])
        fields_padded = fields_size + (-fields_size % 8)
        if body_size > MAX_REPLY_BYTES or 16 + fields_padded + body_size > _MAX_MESSAGE_BYTES:
            raise BusError("message too large")
        raw_fields = self._read_exactly(fields_padded)
        body = self._read_exactly(body_size)
        # Field structs align to 8 from the start of the message, which is
        # also 8-aligned here: the 16 fixed bytes keep the offsets equal.
        reader = _Reader(fixed + raw_fields, little)
        reader.offset = 16
        fields: dict[int, object] = {}
        while reader.offset < 16 + fields_size:
            reader.align(8)
            code = int(reader.fixed("y"))
            fields[code] = reader.value("v")
        return fixed[1], serial, fields, body, little
