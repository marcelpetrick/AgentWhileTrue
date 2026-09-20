# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests for the small deployment shell scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).parents[1]
PROXY = ROOT / "scripts" / "claude-statusline-proxy.sh"
BRIDGE_INSTALLER = ROOT / "scripts" / "install-claude-bridge.sh"
SERVICE_INSTALLER = ROOT / "scripts" / "install-user-service.sh"
USER_SERVICE = ROOT / "systemd" / "agent-while-true.service"
FULL_AUTO = ROOT / "fullAutoMode.sh"
LOCAL_PIPELINE = ROOT / "localPipeline.sh"
QUALITY = ROOT / "scripts" / "quality.sh"


def _run_proxy(
    state_home: Path,
    used: int = 100,
    *,
    chain: str = "",
    claude_pid: int,
    session_id: str = "test-session",
) -> subprocess.CompletedProcess:
    payload = json.dumps(
        {
            "session_id": session_id,
            "usage": {
                "five_hour": {
                    "utilization": used,
                    "resets_at": "2026-09-06T01:20:00Z",
                },
                "seven_day": {"utilization": 42},
            },
        }
    )
    environment = {**os.environ, "XDG_STATE_HOME": str(state_home)}
    environment["AGENT_WHILE_TRUE_CLAUDE_PID"] = str(claude_pid)
    if chain:
        environment["AGENT_WHILE_TRUE_STATUSLINE_CHAIN"] = chain
    return subprocess.run(
        [str(PROXY)], input=payload, text=True, capture_output=True, env=environment, timeout=5
    )


@contextmanager
def _fake_claude(tmp_path: Path) -> Iterator[subprocess.Popen]:
    executable = tmp_path / "claude"
    executable.symlink_to(shutil.which("sleep") or "/usr/bin/sleep")
    process = subprocess.Popen([str(executable), "30"])
    comm = Path("/proc") / str(process.pid) / "comm"
    try:
        # Popen returns as soon as the child is forked, so for a moment /proc
        # still reports the forking interpreter's name instead of "claude".
        deadline = time.monotonic() + 5.0
        while comm.read_text().strip() != "claude":
            assert time.monotonic() < deadline, "the fake claude process never exec()ed"
            time.sleep(0.01)
        yield process
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_statusline_proxy_captures_quota_and_chains_payload(tmp_path: Path) -> None:
    chained = tmp_path / "chained.json"
    with _fake_claude(tmp_path) as claude:
        result = _run_proxy(tmp_path, chain=f"tee {chained}", claude_pid=claude.pid)
    assert result.returncode == 0
    paths = list((tmp_path / "agent-while-true/quota").glob("claude-*.json"))
    assert len(paths) == 1
    captured = json.loads(paths[0].read_text())
    assert captured["source"] == "claude"
    assert captured["process"]["pid"] == claude.pid
    assert len(captured["session_key"]) == 64
    assert captured["five_hour"]["utilization"] == 100
    assert json.loads(chained.read_text())["usage"]["seven_day"]["utilization"] == 42


def test_statusline_proxy_concurrent_writes_remain_valid(tmp_path: Path) -> None:
    with _fake_claude(tmp_path) as claude, ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda used: _run_proxy(tmp_path, used, claude_pid=claude.pid),
                range(90, 106),
            )
        )
    assert all(result.returncode == 0 for result in results)
    paths = list((tmp_path / "agent-while-true/quota").glob("claude-*.json"))
    assert len(paths) == 1
    captured = json.loads(paths[0].read_text())
    assert captured["five_hour"]["utilization"] in range(90, 106)
    assert not list((tmp_path / "agent-while-true/quota").glob("*.tmp.*"))


def test_statusline_proxy_fails_open_on_bad_input(tmp_path: Path) -> None:
    with _fake_claude(tmp_path) as claude:
        result = subprocess.run(
            [str(PROXY)],
            input="not-json",
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "XDG_STATE_HOME": str(tmp_path),
                "AGENT_WHILE_TRUE_CLAUDE_PID": str(claude.pid),
            },
            timeout=5,
        )
    assert result.returncode == 0
    assert not list((tmp_path / "agent-while-true/quota").glob("claude-*.json"))


def test_bridge_installer_preserves_existing_statusline(tmp_path: Path) -> None:
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "statusLine": {
                    "type": "command",
                    "command": "tee /tmp/original",
                    "padding": 2,
                    "refreshInterval": 300,
                }
            }
        )
    )
    result = subprocess.run(
        [str(BRIDGE_INSTALLER)],
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(tmp_path)},
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    status_line = json.loads(settings.read_text())["statusLine"]
    command = status_line["command"]
    assert "AGENT_WHILE_TRUE_CLAUDE_PID=$PPID" in command
    assert "AGENT_WHILE_TRUE_STATUSLINE_CHAIN=" in command
    assert "claude-statusline-proxy.sh" in command
    assert status_line["refreshInterval"] == 60
    assert status_line["padding"] == 2
    assert list(settings.parent.glob("settings.json.agent-while-true-backup.*"))

    again = subprocess.run(
        [str(BRIDGE_INSTALLER)],
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(tmp_path)},
        timeout=5,
    )
    assert again.returncode == 0
    assert "already configured" in again.stdout


def test_bridge_installer_migrates_a_proxy_from_another_namespace(tmp_path: Path) -> None:
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "statusLine": {
                    "type": "command",
                    "command": (
                        "RETIRED_CLAUDE_PID=$PPID "
                        "RETIRED_STATUSLINE_CHAIN=/tmp/original-statusline "
                        "/tmp/retired/claude-statusline-proxy.sh"
                    ),
                    "refreshInterval": 60,
                }
            }
        )
    )

    result = subprocess.run(
        [str(BRIDGE_INSTALLER)],
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(tmp_path)},
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    command = json.loads(settings.read_text())["statusLine"]["command"]
    assert command.startswith("AGENT_WHILE_TRUE_CLAUDE_PID=$PPID ")
    assert "AGENT_WHILE_TRUE_STATUSLINE_CHAIN=/tmp/original-statusline" in command
    assert str(tmp_path / ".local/share/agent-while-true/claude-statusline-proxy.sh") in command
    assert "RETIRED_" not in command
    assert "/tmp/retired/" not in command


def test_user_service_forces_a_utf8_locale_for_qdbus() -> None:
    unit = USER_SERVICE.read_text(encoding="utf-8")
    assert "Environment=LC_ALL=C.UTF-8" in unit


def test_user_service_accepts_the_cli_clean_signal_exit() -> None:
    unit = USER_SERVICE.read_text(encoding="utf-8")
    assert "SuccessExitStatus=130" in unit


def _service_installer_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    cli = home / ".local/bin/agent-while-true"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\nexit 0\n")
    cli.chmod(0o755)

    calls = tmp_path / "systemctl.calls"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{calls}"\n')
    systemctl.chmod(0o755)
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }, calls


def test_service_installer_enables_observe_mode_by_default(tmp_path: Path) -> None:
    environment, calls = _service_installer_environment(tmp_path)
    result = subprocess.run(
        [str(SERVICE_INSTALLER)],
        text=True,
        capture_output=True,
        env=environment,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    unit_dir = Path(environment["HOME"]) / ".config/systemd/user"
    assert (unit_dir / "agent-while-true.service").read_text() == USER_SERVICE.read_text()
    assert not (unit_dir / "agent-while-true.service.d").exists()
    assert "--user enable --now agent-while-true.service" in calls.read_text()
    assert "observe mode" in result.stdout


def test_service_installer_creates_explicit_auto_mode_dropin(tmp_path: Path) -> None:
    environment, calls = _service_installer_environment(tmp_path)
    result = subprocess.run(
        [str(SERVICE_INSTALLER), "--auto", "--allow-codex-auto-resume"],
        text=True,
        capture_output=True,
        env=environment,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    dropin = (
        Path(environment["HOME"])
        / ".config/systemd/user/agent-while-true.service.d/10-agent-while-true-mode.conf"
    ).read_text()
    assert "run --auto --all --no-fzf" in dropin
    assert "Environment=AGENT_WHILE_TRUE_ALLOW_CODEX_AUTO_RESUME=true" in dropin
    assert "Description=Agent While True budget babysitter (auto, Codex enabled)" in dropin
    assert "--user enable --now agent-while-true.service" in calls.read_text()
    assert "auto mode" in result.stdout


def test_service_installer_rejects_codex_opt_in_without_auto(tmp_path: Path) -> None:
    environment, _calls = _service_installer_environment(tmp_path)
    result = subprocess.run(
        [str(SERVICE_INSTALLER), "--allow-codex-auto-resume"],
        text=True,
        capture_output=True,
        env=environment,
        timeout=5,
    )
    assert result.returncode == 2
    assert "requires --auto" in result.stderr


def test_full_auto_launcher_help_is_safe_and_describes_the_gate() -> None:
    result = subprocess.run([str(FULL_AUTO), "--help"], text=True, capture_output=True, timeout=5)
    assert result.returncode == 0
    assert "complete local release pipeline" in result.stdout
    assert "observe-only dashboard" in result.stdout
    assert "Paid" in result.stdout


def test_full_auto_launcher_orders_checks_before_auto_mode() -> None:
    script = FULL_AUTO.read_text(encoding="utf-8")
    setup = script.index("-m pip install --disable-pip-version-check -e '.[dev]'")
    pipeline = script.index("./localPipeline.sh --noRun")
    doctor = script.index('doctor_output="$("$cli" doctor)"')
    status = script.index('"$cli" status')
    quota = script.index('"$cli" quota')
    auto = script.index('exec "$cli" run --auto --all --no-fzf')

    assert setup < pipeline < doctor < status < quota < auto
    assert "AGENT_WHILE_TRUE_ALLOW_CODEX_AUTO_RESUME=true" in script
    assert 'UV_VENV_CLEAR=1 pipx install --force "$wheel"' in script
    assert "run --observe --all --no-fzf" in script
    assert "systemctl --user stop" not in script


def test_canonical_pipeline_covers_required_release_smokes() -> None:
    pipeline = LOCAL_PIPELINE.read_text(encoding="utf-8")
    quality = QUALITY.read_text(encoding="utf-8")

    for command in ("doctor", "status", "quota", "simulate --all"):
        assert command in pipeline
    assert 'agent-while-true" --version' in pipeline
    assert "git --no-pager diff --check" in quality
    assert 'fail "shellcheck (not installed)"' in quality


def test_quality_gate_never_starts_an_interactive_pager() -> None:
    """A gate that can block on a keypress is not a gate.

    `git diff` pages its output, and a developer `LESS` value without `-F`
    keeps that pager open on empty output, so the whole run hung silently.
    """
    quality = QUALITY.read_text(encoding="utf-8")

    assert "git --no-pager diff --check" in quality
    for command in ("git diff", "git log", "git show"):
        assert f"\n    {command}" not in quality


def test_canonical_pipeline_provisions_the_pinned_toolchain_before_checking() -> None:
    pipeline = LOCAL_PIPELINE.read_text(encoding="utf-8")

    assert pipeline.index("\nensure_toolchain\n") < pipeline.index("\nscripts/quality.sh\n")
    # pyproject.toml holds the pins; a second copy here could drift from CI.
    assert "optional-dependencies" in pipeline
    for pin in ("ruff==", "reuse==", "pytest==", "spdx-tools==", "cyclonedx-python-lib"):
        assert pin not in pipeline


def test_canonical_pipeline_help_describes_the_bootstrap() -> None:
    result = subprocess.run(
        [str(LOCAL_PIPELINE), "--help"], text=True, capture_output=True, timeout=10
    )

    assert result.returncode == 0
    assert "pinned quality toolchain" in result.stdout
    assert "AGENT_WHILE_TRUE_TOOLCHAIN_VENV" in result.stdout
