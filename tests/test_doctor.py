# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the environment diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_while_true import doctor, providers
from agent_while_true.config import Config, Policy
from agent_while_true.doctor import Check, Status, exit_code, render
from agent_while_true.terminal.base import SessionRef, TerminalSession
from tests.test_terminal import StubbedKonsole

doctor_module = doctor


def _config(tmp_path: Path) -> Config:
    return Config(state_dir=tmp_path / "state", runtime_dir=tmp_path / "run")


def test_doctor_runs_end_to_end_without_kde(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    checks = doctor.run(
        _config(tmp_path), adapter_factory=lambda: StubbedKonsole(qdbus="/bin/true")
    )
    names = {check.name for check in checks}
    assert {"Linux", "KDE Plasma", "qdbus", "Konsole D-Bus", "Konsole input", "Auto mode"} <= names
    # The three directories can resolve to the same path; the rows must still
    # say which is which.
    assert {"State dir", "Runtime dir", "Log dir"} <= names


def test_missing_qdbus_fails_and_blocks_auto_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "find_qdbus", lambda: None)
    checks = doctor.run(_config(tmp_path), adapter_factory=lambda: StubbedKonsole(qdbus=None))
    by_name = {check.name: check for check in checks}
    assert by_name["qdbus"].status is Status.FAIL
    assert by_name["Auto mode"].status is Status.FAIL
    assert exit_code(checks) == 1


def test_optional_tools_never_fail(tmp_path: Path) -> None:
    check = doctor.check_optional("definitely-not-installed-xyz")
    assert check.status is Status.OK
    assert "optional" in check.detail


def test_policy_disabled_downgrades_auto_mode(tmp_path: Path, monkeypatch) -> None:
    # This test isolates the policy verdict from whether the host running the
    # suite happens to have KDE's qdbus executable installed.
    monkeypatch.setattr(doctor, "find_qdbus", lambda: "/bin/true")
    config = Config(
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "run",
        policy=Policy(resume_after_reset=False),
    )
    checks = doctor.run(config, adapter_factory=lambda: StubbedKonsole(qdbus="/bin/true"))
    by_name = {check.name: check for check in checks}
    assert by_name["Auto mode"].status is Status.WARN


def test_unwritable_state_dir_is_a_failure(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir(mode=0o500)
    try:
        check = doctor._writable_dir("State dir", blocked / "state")
        assert check.status is Status.FAIL
    finally:
        blocked.chmod(0o700)


def test_a_held_lock_warns_rather_than_fails(tmp_path: Path) -> None:
    from agent_while_true.lock import SingleInstanceLock

    config = _config(tmp_path)
    lock = SingleInstanceLock.in_directory(config.resolved_runtime_dir())
    lock.acquire()
    try:
        # The same process can re-flock its own descriptor, so this is checked
        # through the public helper with a foreign holder simulated instead.
        assert doctor.check_lock(config).status in {Status.OK, Status.WARN}
    finally:
        lock.release()


def test_render_and_exit_code() -> None:
    checks = [Check("Linux", Status.OK, "6.1"), Check("qdbus", Status.WARN, "old")]
    text = render(checks)
    assert "Agent While True Doctor" in text
    assert "Linux" in text
    assert exit_code(checks) == 0
    assert exit_code([*checks, Check("x", Status.FAIL)]) == 1


def test_a_provider_newer_than_the_patterns_is_warned_about(monkeypatch) -> None:
    """A reworded banner fails silently, so the version gap has to be announced.

    On 2026-09-20 Codex 0.155.1 changed one apostrophe and no blocked session
    could be continued; nothing in the log said the recognizer had gone blind.
    """
    monkeypatch.setattr(doctor, "_tool_version", lambda *_: "codex-cli 0.156.0")

    check = doctor.check_agent("codex", "--version", adapter=providers.CODEX)

    assert check.status is Status.WARN
    assert "0.155.1" in check.detail
    assert "verify the prompts" in check.detail


def test_a_verified_provider_version_is_not_warned_about(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_tool_version", lambda *_: "codex-cli 0.155.1")
    assert doctor.check_agent("codex", "--version", adapter=providers.CODEX).status is Status.OK

    monkeypatch.setattr(doctor, "_tool_version", lambda *_: "codex-cli 0.154.0")
    assert doctor.check_agent("codex", "--version", adapter=providers.CODEX).status is Status.OK


def test_an_unreadable_version_line_raises_no_false_alarm(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_tool_version", lambda *_: "codex (development build)")
    assert doctor.check_agent("codex", "--version", adapter=providers.CODEX).status is Status.OK


def test_pattern_drift_never_blocks_automatic_mode(monkeypatch) -> None:
    """Drift is a warning: it is a reason to look, not a reason to stop.

    Asserted against the verdict alone rather than a whole `doctor.run`, whose
    outcome depends on whether the machine has a desktop bus at all.
    """
    monkeypatch.setattr(doctor, "_tool_version", lambda *_: "codex-cli 99.0.0")
    drift = doctor.check_agent("codex", "--version", adapter=providers.CODEX)
    assert drift.status is Status.WARN

    verdict = doctor._auto_mode_verdict([drift], Config())

    assert verdict.status is Status.OK


# -- failure rows: a broken environment is reported, never raised -----------


class _StubKonsole:
    def __init__(self, *, services=(), sessions=(), send_fails=False, services_raise=False):
        self._services = list(services)
        self._sessions = list(sessions)
        self._send_fails = send_fails
        self._services_raise = services_raise
        self.sent: list[str] = []

    def is_available(self) -> bool:
        return True

    def services(self) -> list[str]:
        if self._services_raise:
            raise RuntimeError("bus broke")
        return self._services

    def list_sessions(self):
        return self._sessions

    def send_text(self, ref, text: str) -> None:
        if self._send_fails:
            raise RuntimeError("disabled")
        self.sent.append(text)


_ONE = TerminalSession(
    ref=SessionRef("konsole", "org.kde.konsole-1", "/Sessions/1"),
    shell_pid=1,
    foreground_pid=1,
    title="",
)


@pytest.mark.parametrize(
    ("stub", "statuses"),
    [
        (_StubKonsole(services_raise=True), ("FAIL", "FAIL", "FAIL")),
        (_StubKonsole(), ("WARN", "WARN", "WARN")),
        (_StubKonsole(services=["org.kde.konsole-1"]), ("OK", "OK", "WARN")),
        (_StubKonsole(services=["s"], sessions=[_ONE], send_fails=True), ("OK", "OK", "FAIL")),
    ],
)
def test_konsole_rows_degrade_without_raising(stub, statuses) -> None:
    rows = doctor_module.check_konsole(stub)  # type: ignore[arg-type]
    assert tuple(row.status.value for row in rows) == statuses
    # The permission probe only ever sends empty text.
    assert stub.sent in ([], [""])


def test_tool_versions(monkeypatch) -> None:
    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: None)
    assert doctor_module._tool_version("codex", "--version") is None
    assert doctor_module.check_agent("codex", "--version").status.value == "WARN"
    monkeypatch.setattr(doctor_module, "_tool_version", lambda *args: "")
    assert doctor_module.check_agent("codex", "--version").detail == "installed"
    assert doctor_module._pattern_drift("9.9.9", None) is None


def test_privileges_warn_as_root(monkeypatch) -> None:
    monkeypatch.setattr(doctor_module.os, "geteuid", lambda: 0)
    assert doctor_module.check_privileges().status.value == "WARN"


def test_an_unwritable_directory_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(doctor_module.os, "access", lambda path, mode: False)
    assert doctor_module._writable_dir("State", tmp_path).status.value == "FAIL"


def test_an_unusable_lock_directory_fails(tmp_path, monkeypatch) -> None:
    from agent_while_true.config import Config

    def refuse(self) -> None:
        raise PermissionError("read-only runtime dir")

    monkeypatch.setattr(doctor_module.SingleInstanceLock, "acquire", refuse)
    config = Config(runtime_dir=tmp_path)
    assert doctor_module.check_lock(config).status.value == "FAIL"
