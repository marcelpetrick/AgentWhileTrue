# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared fixtures.

The helpers here build ``ProcessInfo`` values that mirror what was observed on a
real Manjaro/KDE machine, so the classifier tests exercise the shapes that
actually occur rather than idealised ones.
"""

from __future__ import annotations

import pytest

from agent_while_true.proc import ProcessIdentity, ProcessInfo


def make_info(
    *,
    pid: int = 1000,
    start_time: int = 123456,
    tty: str = "pts/3",
    exe: str = "/usr/bin/zsh",
    ppid: int = 999,
    comm: str = "zsh",
    cmdline: tuple[str, ...] = ("zsh",),
    cwd: str = "/home/user",
    environ_keys: frozenset[str] = frozenset({"HOME", "PATH"}),
) -> ProcessInfo:
    """Build a ``ProcessInfo`` without touching ``/proc``."""
    return ProcessInfo(
        identity=ProcessIdentity(pid=pid, start_time=start_time, tty=tty, exe=exe),
        ppid=ppid,
        comm=comm,
        cmdline=cmdline,
        cwd=cwd,
        environ_keys=environ_keys,
    )


@pytest.fixture
def info_factory():
    return make_info


@pytest.fixture(autouse=True)
def _isolate_process_tree(monkeypatch):
    """Keep classifier tests off the real process tree by default.

    Individual tests opt back in by patching these again.
    """
    from agent_while_true import classify as classify_module

    monkeypatch.setattr(classify_module, "_child_comms", lambda pid: ())
    monkeypatch.setattr(classify_module, "_ancestor_blocker", lambda info: None)
    monkeypatch.setattr(classify_module, "_detect_container", lambda info: None)


@pytest.fixture(autouse=True)
def _isolate_runtime_dir(tmp_path_factory, monkeypatch):
    """Keep tests away from the runtime directory of a live instance.

    The single-instance lock and the control socket both live there. A test that
    resolved the real ``$XDG_RUNTIME_DIR`` could ask the developer's running
    supervisor to hand over input control, which is exactly the kind of side
    effect a test run must never have.
    """
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("xdg-runtime")))


@pytest.fixture(autouse=True)
def _isolate_proxy_environment(monkeypatch):
    """Keep the host's proxy configuration out of every test.

    ``StatusPageClient`` picks its transport from ``urllib.request.getproxies()``
    at construction time, so a machine or CI runner with ``HTTP_PROXY`` set takes
    the urllib path instead of the persistent-connection path and the status
    tests exercise something other than what they claim.
    """
    from agent_while_true import service_health

    monkeypatch.setattr(service_health.urllib.request, "getproxies", dict)


@pytest.fixture(autouse=True)
def _forget_resolved_accounts():
    """Keep one test's resolved provider accounts out of the next one.

    ``identity`` caches a profile's account for the life of a run so the CLI is
    spawned once rather than once per session; tests need that cache empty.
    """
    from agent_while_true import identity

    identity._CLAUDE_ACCOUNTS.clear()
    yield
    identity._CLAUDE_ACCOUNTS.clear()
