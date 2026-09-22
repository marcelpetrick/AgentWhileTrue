# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for foreground-process classification.

The fixtures mirror processes captured on a live machine: Claude Code 2.1.261
runs as a native binary under ``~/.local/share/claude/versions/``, while Codex
CLI 0.153.2 is a Node shim that execs a native child.
"""

from __future__ import annotations

import pytest

from agent_while_true import classify as classify_module
from agent_while_true.classify import Confidence, ProcessClass, classify
from agent_while_true.proc import ProcessGoneError

#: Captured before the autouse fixture in ``conftest`` replaces it, so the tests
#: below can exercise the real ancestry walk.
_REAL_ANCESTOR_BLOCKER = classify_module._ancestor_blocker

CLAUDE_EXE = "/home/user/.local/share/claude/versions/2.1.261"
CODEX_SHIM = "/run/user/1000/fnm_multishells/631816_1788536739178/bin/codex"
CODEX_NATIVE = (
    "/home/user/.local/share/fnm/node-versions/v20.20.1/installation/lib/node_modules"
    "/@openai/codex/node_modules/@openai/codex-linux-x64/vendor"
    "/x86_64-unknown-linux-musl/bin/codex"
)


def test_real_claude_process_is_automatable(info_factory) -> None:
    info = info_factory(
        comm="claude",
        exe=CLAUDE_EXE,
        cmdline=("claude", "--dangerously-skip-permissions", "--resume"),
    )
    result = classify(info)
    assert result.process_class is ProcessClass.CLAUDE
    assert result.confidence is Confidence.HIGH
    assert result.automatable


def test_codex_node_shim_is_recognised_despite_comm_being_node(info_factory, monkeypatch) -> None:
    monkeypatch.setattr(classify_module, "_child_comms", lambda pid: ("codex",))
    info = info_factory(
        comm="node",
        exe="/home/user/.local/share/fnm/node-versions/v20.20.1/installation/bin/node",
        cmdline=("node", CODEX_SHIM, "--dangerously-bypass-approvals-and-sandbox", "resume"),
    )
    result = classify(info)
    assert result.process_class is ProcessClass.CODEX
    assert result.confidence is Confidence.HIGH
    assert result.automatable


def test_native_codex_child_is_recognised(info_factory) -> None:
    info = info_factory(comm="codex", exe=CODEX_NATIVE, cmdline=(CODEX_NATIVE, "resume"))
    result = classify(info)
    assert result.process_class is ProcessClass.CODEX
    assert result.automatable


@pytest.mark.parametrize("shell", ["zsh", "bash", "fish", "sh"])
def test_idle_shell_is_never_automatable(info_factory, shell: str) -> None:
    result = classify(info_factory(comm=shell, exe=f"/usr/bin/{shell}", cmdline=(shell,)))
    assert result.process_class is ProcessClass.SHELL
    assert not result.automatable
    assert result.blocker == "idle-shell"


def test_ssh_environment_blocks_even_a_convincing_agent(info_factory) -> None:
    info = info_factory(
        comm="claude",
        exe=CLAUDE_EXE,
        cmdline=("claude",),
        environ_keys=frozenset({"SSH_TTY", "SSH_CONNECTION"}),
    )
    result = classify(info)
    assert result.process_class is ProcessClass.SSH
    assert not result.automatable


def test_tmux_environment_blocks_automation(info_factory) -> None:
    info = info_factory(
        comm="claude",
        exe=CLAUDE_EXE,
        cmdline=("claude",),
        environ_keys=frozenset({"TMUX", "TMUX_PANE"}),
    )
    result = classify(info)
    assert result.process_class is ProcessClass.TMUX
    assert not result.automatable


def test_screen_environment_blocks_automation(info_factory) -> None:
    info = info_factory(comm="zsh", environ_keys=frozenset({"STY"}))
    assert classify(info).process_class is ProcessClass.SCREEN


def test_container_marker_blocks_automation(info_factory, monkeypatch) -> None:
    monkeypatch.setattr(classify_module, "_detect_container", lambda info: "container-cgroup")
    result = classify(info_factory(comm="claude", exe=CLAUDE_EXE, cmdline=("claude",)))
    assert result.process_class is ProcessClass.CONTAINER
    assert not result.automatable


def test_tmux_ancestor_blocks_a_genuine_agent(info_factory, monkeypatch) -> None:
    monkeypatch.setattr(
        classify_module, "_ancestor_blocker", lambda info: "nested-terminal-ancestor=tmux"
    )
    result = classify(info_factory(comm="claude", exe=CLAUDE_EXE, cmdline=("claude",)))
    assert result.process_class is ProcessClass.CLAUDE
    assert result.blocker == "nested-terminal-ancestor=tmux"
    assert not result.automatable


def test_a_single_weak_signal_is_not_enough_to_automate(info_factory) -> None:
    # Only one signal: the executable happens to be named `claude`, nothing else
    # corroborates it. The vision requires more than one process field.
    info = info_factory(comm="wrapper", exe="/opt/vendor/claude", cmdline=("wrapper",))
    result = classify(info)
    assert result.process_class is ProcessClass.CLAUDE
    assert result.confidence is Confidence.LOW
    assert not result.automatable


def test_contradictory_evidence_fails_closed(info_factory) -> None:
    info = info_factory(comm="claude", exe=CODEX_NATIVE, cmdline=("claude", "codex"))
    result = classify(info)
    assert result.process_class is ProcessClass.UNKNOWN
    assert result.blocker == "ambiguous-provider-evidence"
    assert not result.automatable


def test_editor_is_blocked(info_factory) -> None:
    result = classify(info_factory(comm="nvim", exe="/usr/bin/nvim", cmdline=("nvim",)))
    assert result.process_class is ProcessClass.EDITOR
    assert not result.automatable


def test_unrecognised_process_fails_closed(info_factory) -> None:
    result = classify(info_factory(comm="btop", exe="/usr/bin/btop", cmdline=("btop",)))
    assert result.process_class is ProcessClass.UNKNOWN
    assert result.blocker == "unrecognised-process"
    assert not result.automatable


def test_an_ancestor_exiting_mid_walk_fails_closed(info_factory, monkeypatch) -> None:
    """A process race in the ancestry must refuse, not raise.

    ``proc.exists`` and the read that follows it are not atomic, so an ancestor
    can exit in between. Losing the ancestry means the supervisor cannot tell
    whether a multiplexer sits between Konsole and this process, and an
    exception here would take the whole supervision loop down with it.
    """

    def gone(pid: int) -> str:
        raise ProcessGoneError(f"/proc/{pid}/comm")

    monkeypatch.setattr(classify_module, "_ancestor_blocker", _REAL_ANCESTOR_BLOCKER)
    monkeypatch.setattr(classify_module.proc, "exists", lambda pid: True)
    monkeypatch.setattr(classify_module.proc, "read_comm", gone)

    result = classify(info_factory(comm="claude", exe=CLAUDE_EXE, cmdline=("claude",)))

    assert result.process_class is ProcessClass.CLAUDE
    assert result.blocker == "ancestor-unreadable"
    assert not result.automatable


def test_an_unreadable_parent_pid_also_fails_closed(info_factory, monkeypatch) -> None:
    def unreadable(pid: int) -> int:
        raise OSError("permission denied")

    monkeypatch.setattr(classify_module, "_ancestor_blocker", _REAL_ANCESTOR_BLOCKER)
    monkeypatch.setattr(classify_module.proc, "exists", lambda pid: True)
    monkeypatch.setattr(classify_module.proc, "read_comm", lambda pid: "zsh")
    monkeypatch.setattr(classify_module.proc, "read_ppid", unreadable)

    result = classify(info_factory(comm="claude", exe=CLAUDE_EXE, cmdline=("claude",)))

    assert result.blocker == "ancestor-unreadable"
    assert not result.automatable


# -- the real environment probes, which conftest replaces by default --------

_REAL_DETECT_CONTAINER = classify_module._detect_container
_REAL_CHILD_COMMS = classify_module._child_comms


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (frozenset({"container"}), "container-environment-marker"),
        (frozenset({"DISTROBOX_ENTER_PATH"}), "container-environment-marker"),
    ],
)
def test_container_environment_markers_block(info_factory, keys, expected) -> None:
    assert _REAL_DETECT_CONTAINER(info_factory(environ_keys=keys)) == expected


@pytest.mark.parametrize(
    ("cgroup", "expected"),
    [
        ("0::/system.slice/docker-abc.scope\n", "container-cgroup"),
        ("0::/user.slice/user-1000.slice/session-2.scope\n", None),
    ],
)
def test_container_cgroups_are_read_from_proc(
    info_factory, tmp_path, monkeypatch, cgroup, expected
) -> None:
    (tmp_path / "1000").mkdir()
    (tmp_path / "1000" / "cgroup").write_text(cgroup)
    monkeypatch.setattr(classify_module.proc, "PROC", tmp_path)
    monkeypatch.setattr(classify_module, "_CONTAINER_FILES", ())
    assert _REAL_DETECT_CONTAINER(info_factory()) == expected


def test_a_container_runtime_file_blocks(info_factory, tmp_path, monkeypatch) -> None:
    marker = tmp_path / ".dockerenv"
    marker.write_text("")
    # No cgroup file at all: an unreadable cgroup is simply not evidence.
    monkeypatch.setattr(classify_module.proc, "PROC", tmp_path)
    monkeypatch.setattr(classify_module, "_CONTAINER_FILES", (marker,))
    assert _REAL_DETECT_CONTAINER(info_factory()) == "container-runtime-file"


def test_a_node_launcher_for_claude_is_a_signal(info_factory) -> None:
    info = info_factory(comm="node", exe="/usr/bin/node", cmdline=("node", "/opt/bin/claude"))
    result = classify(info)
    assert result.process_class is ProcessClass.CLAUDE
    assert "argv1=claude" in result.signals


def test_the_codex_js_shim_script_is_a_signal(info_factory) -> None:
    script = "/usr/lib/node_modules/@openai/codex/bin/codex.js"
    info = info_factory(comm="node", exe="/usr/bin/node", cmdline=("node", script))
    result = classify(info)
    assert result.process_class is ProcessClass.CODEX
    assert "node-shim-script=codex.js" in result.signals


def test_child_comms_skip_children_that_vanish(monkeypatch) -> None:
    def read_comm(pid: int) -> str:
        if pid == 2:
            raise ProcessGoneError(pid)
        return "codex"

    monkeypatch.setattr(classify_module.proc, "children", lambda pid: (2, 3))
    monkeypatch.setattr(classify_module.proc, "read_comm", read_comm)
    assert _REAL_CHILD_COMMS(1) == ("codex",)


def test_child_comms_of_a_vanished_parent_are_empty(monkeypatch) -> None:
    def children(pid: int) -> tuple[int, ...]:
        raise ProcessGoneError(pid)

    monkeypatch.setattr(classify_module.proc, "children", children)
    assert _REAL_CHILD_COMMS(1) == ()


def _ancestry(monkeypatch, chain: dict[int, tuple[str, int]]) -> None:
    """Install a fake process tree: pid -> (comm, ppid)."""
    monkeypatch.setattr(classify_module.proc, "exists", lambda pid: pid in chain)
    monkeypatch.setattr(classify_module.proc, "read_comm", lambda pid: chain[pid][0])
    monkeypatch.setattr(classify_module.proc, "read_ppid", lambda pid: chain[pid][1])


@pytest.mark.parametrize(
    ("chain", "expected"),
    [
        ({999: ("zsh", 998), 998: ("tmux: server", 1)}, None),
        ({999: ("zsh", 998), 998: ("tmux", 1)}, "nested-terminal-ancestor=tmux"),
        ({999: ("zsh", 998), 998: ("sshd", 1)}, "remote-ancestor=sshd"),
        ({999: ("zsh", 998), 998: ("konsole", 997), 997: ("tmux", 1)}, None),
        ({999: ("zsh", 1)}, None),
        ({}, None),
    ],
)
def test_the_ancestry_walk(info_factory, monkeypatch, chain, expected) -> None:
    _ancestry(monkeypatch, chain)
    assert _REAL_ANCESTOR_BLOCKER(info_factory(ppid=999)) == expected


def test_an_endless_ancestry_stops_at_the_depth_limit(info_factory, monkeypatch) -> None:
    # A cycle can only come from a corrupted read; the walk still terminates.
    _ancestry(monkeypatch, {999: ("zsh", 999)})
    assert _REAL_ANCESTOR_BLOCKER(info_factory(ppid=999)) is None
