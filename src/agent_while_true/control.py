# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Control channel between instances of this tool.

The single-instance lock (:mod:`agent_while_true.lock`) guarantees that only one
instance can ever send input. That is correct, but it left a running background
service permanently in charge: a watcher started later at a real keyboard could
never become the input controller, because the lock was already taken.

This channel closes that gap without weakening the guarantee. The instance that
holds the lock listens on a ``AF_UNIX`` socket in the runtime directory, which
``$XDG_RUNTIME_DIR`` already restricts to the owning user. A second instance can
ask it to hand input control over. The holder drops to observe mode and releases
the lock *before* it answers, so at no moment do two instances hold it; the
requester then takes the lock through the ordinary, unchanged path.

The protocol carries no terminal contents, no prompt text and no account data -
only the mode, this process's id, and the version - because a control reply is
just as readable as a log line.
"""

from __future__ import annotations

import contextlib
import json
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

#: Kept beside the lock file, in the same user-private runtime directory.
SOCKET_FILENAME = "agent-while-true.control"

#: A request is one short JSON line; anything longer is a client bug or an
#: attempt to stall the supervisor loop, and is dropped.
_MAX_REQUEST_BYTES = 4096

#: The supervisor polls this socket between scans, so serving a request must
#: never take a meaningful part of a scan interval.
_SERVE_TIMEOUT_SECONDS = 0.25

#: Connections accepted per poll. A queue longer than this is not a legitimate
#: use of a channel whose only clients are the user's own watchers.
_MAX_CONNECTIONS_PER_POLL = 4

#: Request verbs. ``status`` is read-only; ``yield-input`` gives up the lock.
OP_STATUS = "status"
OP_YIELD_INPUT = "yield-input"


class ControlError(RuntimeError):
    """The control channel could not be served or reached."""


#: Handles one request verb and returns the reply payload.
Handler = Callable[[str], dict[str, object]]


@dataclass(slots=True)
class ControlServer:
    """The input controller's request socket.

    It is open exactly while this instance holds the lock, so a client that
    reaches it is by definition talking to the current input controller.
    """

    path: Path
    _sock: socket.socket | None = field(default=None, repr=False)
    _inode: int | None = field(default=None, repr=False)

    @classmethod
    def in_directory(cls, directory: Path) -> ControlServer:
        return cls(path=directory / SOCKET_FILENAME)

    @property
    def active(self) -> bool:
        return self._sock is not None

    def start(self) -> None:
        """Bind and listen, or raise :class:`ControlError`.

        A socket file left behind by a killed instance is replaced, but only
        after a connection attempt proves that nothing is listening on it. A
        live server is never unlinked, so two instances cannot both believe they
        own the channel.
        """
        if self._sock is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            if _is_listening(self.path):
                raise ControlError(f"another instance owns {self.path}")
            self.path.unlink(missing_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(self.path))
            self.path.chmod(0o600)
            sock.listen(_MAX_CONNECTIONS_PER_POLL)
            sock.setblocking(False)
            inode = self.path.stat().st_ino
        except OSError as exc:
            sock.close()
            raise ControlError(f"cannot serve {self.path}: {exc}") from exc
        self._sock = sock
        self._inode = inode

    def poll(self, handler: Handler) -> int:
        """Answer the requests that are already waiting; never block.

        Returns the number of requests served, so the caller can redraw only
        when something actually happened.
        """
        if self._sock is None:
            return 0
        served = 0
        for _ in range(_MAX_CONNECTIONS_PER_POLL):
            try:
                connection, _ = self._sock.accept()
            except BlockingIOError:
                break
            except OSError:
                break
            with connection:
                connection.settimeout(_SERVE_TIMEOUT_SECONDS)
                if _serve_one(connection, handler):
                    served += 1
        return served

    def close(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.close()
        finally:
            self._sock = None
            self._unlink_own_socket()

    def _unlink_own_socket(self) -> None:
        """Remove the socket file only while it is still the one we bound.

        After a handover the successor binds the same path. Comparing the inode
        keeps a departing instance from deleting its successor's socket.
        """
        with contextlib.suppress(OSError):
            if self.path.stat().st_ino == self._inode:
                self.path.unlink(missing_ok=True)
        self._inode = None


def _serve_one(connection: socket.socket, handler: Handler) -> bool:
    """Read one request line, hand it to ``handler`` and write the reply."""
    try:
        line = _read_line(connection)
    except (OSError, ControlError):
        return False
    try:
        request = json.loads(line)
        op = str(request["op"])
    except (ValueError, KeyError, TypeError):
        _send(connection, {"ok": False, "reason": "malformed-request"})
        return False
    reply = handler(op)
    _send(connection, reply)
    return bool(reply.get("ok"))


def _read_line(connection: socket.socket) -> str:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = connection.recv(1024)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if b"\n" in chunk:
            break
        if size > _MAX_REQUEST_BYTES:
            raise ControlError("request too long")
    return b"".join(chunks).split(b"\n", 1)[0].decode("utf-8", "replace")


def _send(connection: socket.socket, payload: dict[str, object]) -> None:
    with_newline = json.dumps(payload).encode("utf-8") + b"\n"
    # The client may have given up. Nothing this instance decides depends on the
    # reply arriving, so a failed send needs no recovery.
    with contextlib.suppress(OSError):
        connection.sendall(with_newline)


def _is_listening(path: Path) -> bool:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(_SERVE_TIMEOUT_SECONDS)
        try:
            probe.connect(str(path))
        except OSError:
            return False
        return True


def request(path: Path, op: str, *, timeout: float = 5.0) -> dict[str, object]:
    """Send one request to the input controller and return its reply."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect(str(path))
            sock.sendall(json.dumps({"op": op}).encode("utf-8") + b"\n")
            line = _read_line(sock)
        except OSError as exc:
            raise ControlError(f"no input controller at {path}: {exc}") from exc
    try:
        reply = json.loads(line)
    except ValueError as exc:
        raise ControlError("malformed reply from the input controller") from exc
    if not isinstance(reply, dict):
        raise ControlError("malformed reply from the input controller")
    return reply


def request_yield_input(runtime_dir: Path, *, timeout: float = 5.0) -> tuple[bool, str]:
    """Ask the current input controller to give up the lock.

    Returns whether it did, plus a short reason suitable for the status line.
    A refusal is normal and safe: the other instance keeps input control.
    """
    socket_path = runtime_dir / SOCKET_FILENAME
    try:
        reply = request(socket_path, OP_YIELD_INPUT, timeout=timeout)
    except ControlError as exc:
        return False, str(exc)
    if reply.get("ok"):
        return True, str(reply.get("detail", "input control handed over"))
    return False, str(reply.get("reason", "refused"))
