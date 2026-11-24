# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""KDE Konsole adapter, driven through Konsole's per-session D-Bus interface.

Using Konsole's own interface rather than desktop-wide input simulation is what
makes this work under Wayland: no ``xdotool``, no ``ydotool``, no screen
coordinates, no OCR. The methods used here were verified against Konsole on
Manjaro/KDE Plasma with ``XDG_SESSION_TYPE=wayland``:

``org.kde.konsole.Session``
    ``processId``, ``foregroundProcessId``, ``getDisplayedTextList``,
    ``getAllDisplayedTextList``, ``sendText``, ``title``.

Reads go over one persistent session-bus connection (``terminal/dbus.py``),
rendered exactly as qdbus prints them; ``sendText`` always launches qdbus.
"""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from agent_while_true.terminal.base import (
    DEFAULT_VISIBLE_LINES,
    SessionRef,
    TerminalAdapter,
    TerminalSession,
    TerminalUnavailableError,
)
from agent_while_true.terminal.dbus import BusCallError, BusError, SessionBus

ADAPTER_NAME = "konsole"

_SERVICE_RE = re.compile(r"^org\.kde\.konsole(?:-\d+)?$")
_SESSION_PATH_RE = re.compile(r"^/Sessions/\d+$")

#: Preferred first; ``qdbus6`` is the Qt6 name shipped by current KDE, ``qdbus``
#: the traditional one. Either is acceptable.
_QDBUS_CANDIDATES = ("qdbus6", "qdbus", "qdbus-qt6", "qdbus-qt5")

#: Each call also launches qdbus; measured healthy end-to-end calls take several
#: milliseconds. Anything near this bound means the session should be skipped.
_CALL_TIMEOUT_SECONDS = 5.0

#: The read-only calls answered on the persistent bus connection, by method:
#: argument signature, and how qdbus would have spelled each argument. Every
#: other call - above all ``sendText``, the one that types - keeps using qdbus.
_NATIVE_SESSION_METHODS = {
    "processId": "",
    "foregroundProcessId": "",
    "title": "i",
    "getAllDisplayedTextList": "b",
}

#: Konsole's Session.title() takes a role; 1 is the display/tab title.
_TITLE_ROLE_DISPLAY = 1

#: Default for :attr:`KonsoleAdapter.qdbus`. A distinct sentinel is needed so
#: that passing ``qdbus=None`` explicitly means "there is no qdbus here" - which
#: tests and ``doctor`` rely on - rather than "go and look for one".
AUTODETECT = "<autodetect>"


def find_qdbus() -> str | None:
    """Return the qdbus executable to use, or ``None`` if none is installed."""
    for candidate in _QDBUS_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
    return None


@dataclass(slots=True)
class KonsoleAdapter(TerminalAdapter):
    """Talk to every running Konsole instance on the current user's bus."""

    qdbus: str | None = AUTODETECT
    name: str = ADAPTER_NAME
    #: The persistent session-bus connection for read-only calls; ``None``
    #: (no usable address, as in the test suite) means qdbus for everything.
    bus: SessionBus | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.qdbus == AUTODETECT:
            self.qdbus = find_qdbus()
            # Only the autodetecting production adapter talks to the real bus;
            # an explicitly given qdbus (tests, doctor) is used for every call.
            if self.bus is None and self.qdbus is not None:
                self.bus = SessionBus.from_environment(timeout=_CALL_TIMEOUT_SECONDS)

    # -- plumbing ---------------------------------------------------------

    def _call(self, *args: str) -> str | None:
        """Run one call, rendered as qdbus prints it. ``None`` when it failed.

        Failure is routine - a tab can close between enumeration and use - so it
        is reported as ``None`` rather than raised, and the caller drops that
        session from the current scan. Read-only calls go over the persistent
        bus connection when there is one; a transport failure there falls back
        to qdbus for that call, while a D-Bus error reply is the call's answer.
        """
        if self.qdbus is None:
            raise TerminalUnavailableError("no qdbus executable found")
        if self.bus is not None:
            try:
                native = self._native_call(args)
            except BusCallError:
                return None
            except BusError:
                native = None
            if native is not None:
                return native
        return self._qdbus_call(args)

    def _native_call(self, args: tuple[str, ...]) -> str | None:
        """The bus-connection version of a qdbus call, or ``None`` if not one."""
        assert self.bus is not None
        if not args:
            _, values = self.bus.call(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ListNames",
            )
            return _qdbus_text(values)
        if len(args) == 1:
            # qdbus SERVICE lists object paths; only the sessions are wanted.
            _, values = self.bus.call(
                args[0], "/Sessions", "org.freedesktop.DBus.Introspectable", "Introspect"
            )
            if len(values) != 1 or not isinstance(values[0], str):
                raise BusError("unexpected introspection reply")
            try:
                nodes = ET.fromstring(values[0]).findall("node")
            except ET.ParseError as exc:
                raise BusError("malformed introspection data") from exc
            return "".join(f"/Sessions/{node.get('name', '')}\n" for node in nodes)
        service, path, method, *rest = args
        interface, _, member = method.rpartition(".")
        signature = _NATIVE_SESSION_METHODS.get(member)
        if interface != "org.kde.konsole.Session" or signature is None:
            return None
        if len(rest) != len(signature):
            return None
        converted: list[object] = []
        for code, text in zip(signature, rest, strict=True):
            if code == "b" and text in {"true", "false"}:
                converted.append(text == "true")
            elif code == "i" and text.lstrip("-").isdecimal():
                converted.append(int(text))
            else:
                return None
        _, values = self.bus.call(service, path, interface, member, signature, tuple(converted))
        return _qdbus_text(values)

    def _qdbus_call(self, args: tuple[str, ...]) -> str | None:
        assert self.qdbus is not None
        try:
            # Fixed executable, fixed argument vector, no shell: nothing is
            # interpolated into a command line.
            completed = subprocess.run(
                [self.qdbus, *args],
                capture_output=True,
                text=True,
                timeout=_CALL_TIMEOUT_SECONDS,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout

    # -- adapter interface -------------------------------------------------

    def is_available(self) -> bool:
        if self.qdbus is None:
            return False
        return self._call() is not None

    def services(self) -> list[str]:
        """Return every Konsole D-Bus service name currently on the bus."""
        raw = self._call()
        if raw is None:
            raise TerminalUnavailableError("cannot list D-Bus services")
        names = {
            stripped for line in raw.splitlines() if _SERVICE_RE.match(stripped := line.strip())
        }
        # Oldest Konsole process first, whichever transport listed the names:
        # dashboard rows follow discovery order and must not reshuffle.
        return sorted(
            names, key=lambda name: int(name.removeprefix("org.kde.konsole").lstrip("-") or 0)
        )

    def _session_paths(self, service: str) -> list[str]:
        raw = self._call(service)
        if raw is None:
            return []
        return [
            stripped
            for line in raw.splitlines()
            if _SESSION_PATH_RE.match(stripped := line.strip())
        ]

    def _int_call(self, ref: SessionRef, method: str) -> int:
        raw = self._call(ref.service, ref.session_id, f"org.kde.konsole.Session.{method}")
        if raw is None:
            return 0
        try:
            return int(raw.strip())
        except ValueError:
            return 0

    def list_sessions(self) -> list[TerminalSession]:
        return self._list_sessions(include_titles=True)

    def list_sessions_brief(self) -> list[TerminalSession]:
        return self._list_sessions(include_titles=False)

    def _list_sessions(self, *, include_titles: bool) -> list[TerminalSession]:
        sessions: list[TerminalSession] = []
        for service in self.services():
            for path in self._session_paths(service):
                ref = SessionRef(adapter=self.name, service=service, session_id=path)
                shell_pid = self._int_call(ref, "processId")
                if shell_pid == 0:
                    # The tab closed between enumeration and inspection.
                    continue
                foreground_pid = self._int_call(ref, "foregroundProcessId") or shell_pid
                title = (
                    self._call(
                        service, path, "org.kde.konsole.Session.title", str(_TITLE_ROLE_DISPLAY)
                    )
                    if include_titles
                    else ""
                )
                sessions.append(
                    TerminalSession(
                        ref=ref,
                        shell_pid=shell_pid,
                        foreground_pid=foreground_pid,
                        title=(title or "").strip(),
                    )
                )
        return sessions

    def foreground_pid(self, ref: SessionRef) -> int:
        return self._int_call(ref, "foregroundProcessId")

    def read_visible_text(self, ref: SessionRef, lines: int = DEFAULT_VISIBLE_LINES) -> list[str]:
        raw = self._call(
            ref.service,
            ref.session_id,
            "org.kde.konsole.Session.getAllDisplayedTextList",
            "true",
        )
        if raw is None:
            return []
        rows = raw.splitlines()
        # Konsole returns every row of the window. A screen shorter than the
        # window sits on the top rows with blank padding below it, and a tail
        # of padding alone hid a live permission prompt on 2026-09-28. The
        # padding is not content, so it is dropped before the tail is taken.
        while rows and not rows[-1].strip():
            rows.pop()
        # Only the tail is kept. Older lines are exactly the "historical prompt
        # text" hazard the vision warns about (DANGER 3), and keeping them would
        # also mean holding more terminal content in memory than necessary.
        return rows[-lines:]

    def send_text(self, ref: SessionRef, text: str) -> None:
        result = self._call(ref.service, ref.session_id, "org.kde.konsole.Session.sendText", text)
        if result is None:
            raise TerminalUnavailableError(f"sendText failed for {ref.key()}")


def _qdbus_text(values: list[object]) -> str:
    """Print reply values the way qdbus does: one line per value or element."""
    lines: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, bool):
                lines.append("true" if item else "false")
            elif isinstance(item, int | str):
                lines.append(str(item))
            else:
                raise BusError("unexpected reply type")
    return "".join(f"{line}\n" for line in lines)
