# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests for the small deployment shell scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).parents[1]
PROXY = ROOT / "scripts" / "claude-statusline-proxy.sh"
BRIDGE_INSTALLER = ROOT / "scripts" / "install-claude-bridge.sh"
USER_SERVICE = ROOT / "systemd" / "agent-watch.service"
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
    environment["AGENT_WATCH_CLAUDE_PID"] = str(claude_pid)
    if chain:
        environment["AGENT_WATCH_STATUSLINE_CHAIN"] = chain
    return subprocess.run(
        [str(PROXY)], input=payload, text=True, capture_output=True, env=environment, timeout=5
    )


@contextmanager
def _fake_claude(tmp_path: Path) -> Iterator[subprocess.Popen]:
    executable = tmp_path / "claude"
    executable.symlink_to(shutil.which("sleep") or "/usr/bin/sleep")
    process = subprocess.Popen([str(executable), "30"])
    try:
        assert (Path("/proc") / str(process.pid) / "comm").read_text().strip() == "claude"
        yield process
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_statusline_proxy_captures_quota_and_chains_payload(tmp_path: Path) -> None:
    chained = tmp_path / "chained.json"
    with _fake_claude(tmp_path) as claude:
        result = _run_proxy(tmp_path, chain=f"tee {chained}", claude_pid=claude.pid)
    assert result.returncode == 0
    paths = list((tmp_path / "agent-watch/quota").glob("claude-*.json"))
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
    paths = list((tmp_path / "agent-watch/quota").glob("claude-*.json"))
    assert len(paths) == 1
    captured = json.loads(paths[0].read_text())
    assert captured["five_hour"]["utilization"] in range(90, 106)
    assert not list((tmp_path / "agent-watch/quota").glob("*.tmp.*"))


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
                "AGENT_WATCH_CLAUDE_PID": str(claude.pid),
            },
            timeout=5,
        )
    assert result.returncode == 0
    assert not list((tmp_path / "agent-watch/quota").glob("claude-*.json"))


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
    assert "AGENT_WATCH_CLAUDE_PID=$PPID" in command
    assert "AGENT_WATCH_STATUSLINE_CHAIN=" in command
    assert "claude-statusline-proxy.sh" in command
    assert status_line["refreshInterval"] == 60
    assert status_line["padding"] == 2
    assert list(settings.parent.glob("settings.json.agent-watch-backup.*"))

    again = subprocess.run(
        [str(BRIDGE_INSTALLER)],
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(tmp_path)},
        timeout=5,
    )
    assert again.returncode == 0
    assert "already configured" in again.stdout


def test_user_service_forces_a_utf8_locale_for_qdbus() -> None:
    unit = USER_SERVICE.read_text(encoding="utf-8")
    assert "Environment=LC_ALL=C.UTF-8" in unit


def test_user_service_accepts_the_cli_clean_signal_exit() -> None:
    unit = USER_SERVICE.read_text(encoding="utf-8")
    assert "SuccessExitStatus=130" in unit


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
    assert "AGENT_WATCH_ALLOW_CODEX_AUTO_RESUME=true" in script
    assert 'UV_VENV_CLEAR=1 pipx install --force "$wheel"' in script
    assert "run --observe --all --no-fzf" in script
    assert "systemctl --user stop" not in script


def test_canonical_pipeline_covers_required_release_smokes() -> None:
    pipeline = LOCAL_PIPELINE.read_text(encoding="utf-8")
    quality = QUALITY.read_text(encoding="utf-8")

    for command in ("doctor", "status", "quota", "simulate --all"):
        assert command in pipeline
    assert 'agent-watch" --version' in pipeline
    assert "git diff --check" in quality
    assert 'fail "shellcheck (not installed)"' in quality
