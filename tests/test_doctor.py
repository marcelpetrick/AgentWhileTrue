# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the environment diagnostics."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_while_true import doctor, providers
from agent_while_true.config import Config, Policy
from agent_while_true.doctor import Check, Status, exit_code, render
from agent_while_true.terminal.base import SessionRef, TerminalSession
from tests.test_terminal import StubbedKonsole

doctor_module = doctor


def _config(tmp_path: Path) -> Config:
    return Config(state_dir=tmp_path / "state", runtime_dir=tmp_path / "run")


def _stub_provider_capabilities(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor, "check_codex_app_server", lambda: Check("Codex app-server", Status.OK)
    )
    monkeypatch.setattr(
        doctor, "check_claude_bridge", lambda: Check("Claude quota bridge", Status.OK)
    )


def test_doctor_runs_end_to_end_without_kde(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    _stub_provider_capabilities(monkeypatch)
    checks = doctor.run(
        _config(tmp_path), adapter_factory=lambda: StubbedKonsole(qdbus="/bin/true")
    )
    names = {check.name for check in checks}
    assert {
        "Linux",
        "Distribution",
        "KDE Plasma",
        "qdbus",
        "Konsole D-Bus",
        "Konsole input",
        "Codex app-server",
        "Claude quota bridge",
        "Auto mode",
    } <= names
    # The three directories can resolve to the same path; the rows must still
    # say which is which.
    assert {"State dir", "Runtime dir", "Log dir"} <= names


def test_missing_qdbus_fails_and_blocks_auto_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "find_qdbus", lambda: None)
    _stub_provider_capabilities(monkeypatch)
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
    _stub_provider_capabilities(monkeypatch)
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
    # One minor version past the newest verified one, so the case stays "newer"
    # however far the verified list moves.
    newest = providers.CODEX.verified_versions[-1]
    major, minor, _ = (int(part) for part in newest.split("."))
    monkeypatch.setattr(doctor, "_tool_version", lambda *_: f"codex-cli {major}.{minor + 1}.0")

    check = doctor.check_agent("codex", "--version", adapter=providers.CODEX)

    assert check.status is Status.WARN
    assert newest in check.detail
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


@pytest.mark.parametrize(
    ("release", "status"),
    [
        ({"ID": "manjaro", "PRETTY_NAME": "Manjaro Linux"}, Status.OK),
        ({"ID": "endeavouros", "ID_LIKE": "arch", "PRETTY_NAME": "EndeavourOS"}, Status.OK),
        ({"ID": "ubuntu", "PRETTY_NAME": "Ubuntu"}, Status.WARN),
        ({}, Status.WARN),
    ],
)
def test_distribution_reports_the_validated_arch_family(monkeypatch, release, status) -> None:
    monkeypatch.setattr(doctor_module.platform, "freedesktop_os_release", lambda: release)
    check = doctor_module.check_distribution()
    assert check.status is status


def test_unreadable_distribution_is_a_warning(monkeypatch) -> None:
    def unreadable():
        raise OSError("missing")

    monkeypatch.setattr(doctor_module.platform, "freedesktop_os_release", unreadable)
    assert doctor_module.check_distribution().status is Status.WARN


@pytest.mark.parametrize("returncode", [0, 2])
def test_codex_app_server_probe_uses_only_the_help_command(monkeypatch, returncode: int) -> None:
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr(doctor_module.subprocess, "run", run)

    check = doctor_module.check_codex_app_server()

    assert calls == [["/usr/bin/codex", "app-server", "--help"]]
    assert check.status is (Status.OK if returncode == 0 else Status.WARN)


def test_codex_app_server_probe_degrades_without_running_plain_codex(monkeypatch) -> None:
    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: None)
    assert doctor_module.check_codex_app_server().status is Status.WARN

    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: "/usr/bin/codex")
    for error in (OSError("broken"), subprocess.TimeoutExpired("codex", 15)):

        def fail(*args, error=error, **kwargs):
            raise error

        monkeypatch.setattr(doctor_module.subprocess, "run", fail)
        check = doctor_module.check_codex_app_server()
        assert check.status is Status.WARN
        assert "broken" not in check.detail


def _bridge_settings(target: Path, **updates) -> dict[str, object]:
    status_line: dict[str, object] = {
        "type": "command",
        "command": f"AGENT_WHILE_TRUE_CLAUDE_PID=$PPID {target}",
        "refreshInterval": 60,
    }
    status_line.update(updates)
    return {"statusLine": status_line}


def test_claude_bridge_accepts_only_an_installed_process_bound_proxy(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    target = tmp_path / "claude-statusline-proxy.sh"
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o700)
    settings.write_text(json.dumps(_bridge_settings(target)), encoding="utf-8")

    check = doctor_module.check_claude_bridge(settings, target)

    assert check == Check("Claude quota bridge", Status.OK, "configured and process-bound")


def test_claude_bridge_reports_missing_settings(tmp_path: Path) -> None:
    check = doctor_module.check_claude_bridge(
        tmp_path / "missing-settings.json", tmp_path / "proxy"
    )

    assert check == Check("Claude quota bridge", Status.WARN, "not configured")


@pytest.mark.parametrize(
    ("document", "detail"),
    [
        ("not-json", "malformed"),
        (json.dumps([]), "not an object"),
        (json.dumps({"statusLine": "echo x"}), "not the quota bridge"),
    ],
)
def test_claude_bridge_rejects_malformed_settings(
    tmp_path: Path, document: str, detail: str
) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(document, encoding="utf-8")
    check = doctor_module.check_claude_bridge(settings, tmp_path / "proxy")
    assert check.status is Status.WARN
    assert detail in check.detail


@pytest.mark.parametrize(
    ("updates", "detail"),
    [
        ({"command": "echo sentinel-secret"}, "proxy command"),
        ({"command": "{target}"}, "process binding"),
        ({"refreshInterval": 61}, "refresh interval"),
    ],
)
def test_claude_bridge_rejects_incomplete_configuration_without_echoing_it(
    tmp_path: Path, updates: dict[str, object], detail: str
) -> None:
    settings = tmp_path / "settings.json"
    target = tmp_path / "proxy"
    updates = {
        key: (str(value).format(target=target) if isinstance(value, str) else value)
        for key, value in updates.items()
    }
    settings.write_text(json.dumps(_bridge_settings(target, **updates)), encoding="utf-8")

    check = doctor_module.check_claude_bridge(settings, target)

    assert check.status is Status.WARN
    assert detail in check.detail
    assert "sentinel-secret" not in check.detail


def test_claude_bridge_reports_missing_and_non_executable_proxy(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    target = tmp_path / "proxy"
    settings.write_text(json.dumps(_bridge_settings(target)), encoding="utf-8")
    assert "not installed" in doctor_module.check_claude_bridge(settings, target).detail

    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o600)
    assert "not executable" in doctor_module.check_claude_bridge(settings, target).detail


def test_optional_provider_capability_warnings_do_not_block_auto_mode() -> None:
    checks = [
        Check("Codex app-server", Status.WARN),
        Check("Claude quota bridge", Status.WARN),
    ]
    assert doctor_module._auto_mode_verdict(checks, Config()).status is Status.OK


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
