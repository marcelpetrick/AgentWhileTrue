# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Codex's rate-limit model-switch dialog: always keep the current model.

Live 2026-11-11 17:41, Codex CLI 0.167.0: the dialog "Approaching rate limits -
Switch to gpt-6-luna for lower credit usage?" covered the usage-limit composer
with the cursor on the downgrade. The downgrade veto kept it manual, so the
timed continuation behind it never ran. The maintainer asked that these choices
always keep the model: only "2. Keep current model" is ever selected (Down,
Enter), never the switch and never "never show again", which changes a setting.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agent_while_true import providers
from agent_while_true.config import Config, Mode, Policy
from agent_while_true.fsm import KEEP_MODEL_KEYSTROKES, Supervisor
from agent_while_true.states import SessionState
from tests import screens
from tests.harness import build

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 11, 17, 41, tzinfo=BERLIN)
DIALOG = screens.CODEX_0_167_KEEP_MODEL_DIALOG
TAB = "/Sessions/1"


def test_live_dialog_is_the_exact_keep_model_prompt() -> None:
    result = providers.CODEX.recognise(DIALOG, now=NOW)

    assert result.keep_model_fingerprint
    assert result.action is None  # never a resume, never typed text
    assert not result.retry_prompt
    assert not result.composer_empty
    assert "codex/model-downgrade" in result.matched_ids


def test_after_keeping_the_model_the_limit_composer_is_the_retry_prompt() -> None:
    result = providers.CODEX.recognise(screens.CODEX_0_167_LIMIT_AFTER_KEEP_MODEL, now=NOW)

    assert not result.keep_model_fingerprint
    assert result.retry_prompt
    assert result.state is SessionState.LIMIT_BLOCKED


def _swap(old: str, new: str) -> list[str]:
    assert any(old in line for line in DIALOG)
    return [line.replace(old, new) for line in DIALOG]


GLYPH = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
NEVER = "Keep current model (never show again)"


@pytest.mark.parametrize(
    "screen",
    [
        pytest.param(_swap(f"{GLYPH} 1.", "  1."), id="no-cursor"),
        pytest.param(
            [
                line.replace(f"{GLYPH} 1.", "  1.").replace("  2. Keep", f"{GLYPH} 2. Keep")
                for line in DIALOG
            ],
            id="cursor-on-keep",
        ),
        pytest.param(_swap(NEVER, "Upgrade to Pro"), id="paid-item"),
        pytest.param(_swap("  2. Keep current model", "  2. Use credits"), id="item-2-reworded"),
        pytest.param(_swap("gpt-6-luna for", "gpt-6-sol for"), id="model-mismatch"),
        pytest.param(_swap("Approaching rate limits", "Choose a model"), id="other-title"),
        pytest.param(_swap("enter select · esc back", "enter confirm"), id="other-footer"),
        pytest.param([*DIALOG[:-1], "  4. Something else", DIALOG[-1]], id="extra-row"),
        pytest.param([*DIALOG, f"{GLYPH} half a draft"], id="composer-below"),
        pytest.param(DIALOG[:-1], id="no-footer"),
    ],
)
def test_every_other_shape_stays_manual(screen: list[str]) -> None:
    assert not providers.CODEX.recognise(screen, now=NOW).keep_model_fingerprint


def _kit(tmp_path, *, mode: Mode = Mode.AUTO, policy: Policy | None = None, screen=None):
    kit = build(tmp_path, now=NOW, config=Config(mode=mode, policy=policy or Policy()))
    info = kit.inspector.add_codex(3421)
    ref = kit.terminal.add(
        TAB, shell_pid=100, foreground_pid=info.pid, screen=list(screen or DIALOG)
    )
    kit.supervisor.select(ref, info.identity, "codex", "synthetic")
    return kit, kit.supervisor.sessions[ref.key()]


def _log(tmp_path) -> str:
    return (tmp_path / "agent-while-true.log").read_text(encoding="utf-8")


def test_full_auto_keeps_the_model_once_per_appearance(tmp_path) -> None:
    kit, _ = _kit(tmp_path)

    decision = kit.supervisor.tick()[0]
    assert decision.reason == "model-kept"
    assert kit.sent == [(TAB, KEEP_MODEL_KEYSTROKES)]
    assert KEEP_MODEL_KEYSTROKES == "\x1b[B\r"

    kit.clock.advance(1)
    kit.supervisor.tick()  # still drawn: no second keypress inside the settle time
    assert len(kit.sent) == 1
    log = _log(tmp_path)
    assert "event=model_kept" in log
    assert "gpt-6-luna" not in log


def test_dialog_still_there_after_settling_is_reported_once_never_repressed(tmp_path) -> None:
    kit, session = _kit(tmp_path)
    kit.supervisor.tick()
    for _ in range(4):
        kit.clock.advance(4)
        decision = kit.supervisor.tick()[0]

    assert len(kit.sent) == 1
    assert decision.reason == "keep-model-unanswered"
    assert _log(tmp_path).count("reason=keep-model-unanswered") == 1
    assert session.keep_model_stuck


def test_dialog_returning_after_it_closed_is_answered_again(tmp_path) -> None:
    kit, _ = _kit(tmp_path)
    kit.supervisor.tick()
    kit.terminal.set_screen(TAB, list(screens.CODEX_0_167_LIMIT_AFTER_KEEP_MODEL))
    kit.clock.advance(5)
    kit.supervisor.tick()
    kit.terminal.set_screen(TAB, list(DIALOG))
    kit.clock.advance(5)
    kit.supervisor.tick()

    assert [text for _, text in kit.sent].count(KEEP_MODEL_KEYSTROKES) == 2


@pytest.mark.parametrize(
    ("mode", "policy", "reason"),
    [
        (Mode.OBSERVE, Policy(), "observe-mode"),
        (Mode.ASK, Policy(), "keep-model-requires-full-auto"),
        (Mode.AUTO, Policy(allow_keep_current_model=False), "keep-model-disabled"),
    ],
    ids=["observe", "ask", "switched-off"],
)
def test_nothing_is_pressed_outside_full_auto_or_when_switched_off(
    tmp_path, mode, policy, reason
) -> None:
    kit, _ = _kit(tmp_path, mode=mode, policy=policy)

    assert kit.supervisor.tick()[0].reason == reason
    assert kit.sent == []


def test_a_replacement_process_is_never_pressed(tmp_path) -> None:
    kit, _ = _kit(tmp_path)
    replacement = kit.inspector.add_codex(9999, start_time=777)
    kit.terminal.sessions[TAB].foreground_pid = replacement.identity.pid

    kit.supervisor.tick()

    assert kit.sent == []


def test_a_dialog_changing_before_the_keypress_is_not_pressed(tmp_path) -> None:
    kit, _ = _kit(tmp_path)
    original = Supervisor.observe
    calls = {"n": 0}

    def drifting(self, ref, *, now=None):
        calls["n"] += 1
        if calls["n"] == 2:  # the revalidating read sees a different dialog
            kit.terminal.set_screen(
                TAB, [line.replace("gpt-6-luna", "gpt-6-mini") for line in DIALOG]
            )
        return original(self, ref, now=now)

    Supervisor.observe = drifting  # type: ignore[method-assign]
    try:
        decision = kit.supervisor.tick()[0]
    finally:
        Supervisor.observe = original  # type: ignore[method-assign]

    assert decision.reason == "revalidation-failed:prompt-changed"
    assert kit.sent == []


def test_then_the_timed_continuation_runs_after_the_reset(tmp_path) -> None:
    policy = Policy(allow_codex_auto_resume=True)
    kit, _ = _kit(tmp_path, policy=policy)
    kit.supervisor.tick()
    assert kit.sent == [(TAB, KEEP_MODEL_KEYSTROKES)]
    kit.terminal.set_screen(TAB, list(screens.CODEX_0_167_LIMIT_AFTER_KEEP_MODEL))
    for _ in range(3):
        kit.clock.advance(kit.supervisor.config.retry_schedule[0])
        kit.supervisor.tick()

    assert any("continue" in text for _, text in kit.sent[1:])


TODAY_RESET = datetime(2026, 11, 11, 14, 8, tzinfo=BERLIN)


def test_the_dialog_carries_the_banner_reset_so_it_is_anchored_while_open() -> None:
    assert providers.CODEX.recognise(DIALOG, now=NOW).reset_at == TODAY_RESET


def test_a_past_bare_codex_clock_has_passed_today_not_tomorrow() -> None:
    # Codex prints a bare clock only for a same-day reset ("Nov 11th, 2026
    # 2:48 AM" otherwise), so 2:08 PM seen at 17:41 was today's 14:08.
    result = providers.CODEX.recognise(screens.CODEX_0_167_LIMIT_AFTER_KEEP_MODEL, now=NOW)

    assert result.reset_at == TODAY_RESET


def test_claude_bare_clocks_still_roll_forward() -> None:
    from agent_while_true.providers.timeparse import parse_reset

    assert parse_reset("resets 2:08pm", NOW) == datetime(2026, 11, 12, 14, 8, tzinfo=BERLIN)
    assert parse_reset("resets 2:08pm", NOW, same_day=True) == TODAY_RESET


def test_live_case_first_seen_after_the_reset_continues_on_the_first_backoff(tmp_path) -> None:
    """The stuck tab: dialog first seen at 17:41, hours after its 14:08 reset."""
    kit, session = _kit(tmp_path, policy=Policy(allow_codex_auto_resume=True))
    kit.supervisor.tick()
    assert session.reset_at == TODAY_RESET
    kit.terminal.set_screen(TAB, list(screens.CODEX_0_167_LIMIT_AFTER_KEEP_MODEL))
    kit.clock.advance(kit.supervisor.config.retry_schedule[0])
    kit.supervisor.tick()

    assert kit.sent[-1][1] == "\x1b[200~continue\x1b[201~\r"


@pytest.mark.e2e
def test_real_pty_reports_the_kept_model(tmp_path) -> None:
    import re
    from pathlib import Path

    from tests.pty_dashboard import Dashboard

    def flat(text: str) -> str:
        plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
        return " ".join(plain.replace("│", " ").split())

    dashboard = Dashboard(
        tmp_path, "--no-color", driver=Path(__file__).with_name("pty_keep_model.py")
    )
    try:
        dashboard.read_until(lambda text: "Kept the current model" in flat(text), timeout=20)
    finally:
        assert dashboard.quit() == 0


def test_an_unverified_continuation_is_verified_before_the_dialog_is_answered(tmp_path) -> None:
    kit, session = _kit(
        tmp_path,
        policy=Policy(allow_codex_auto_resume=True),
        screen=screens.CODEX_0_167_LIMIT_AFTER_KEEP_MODEL,
    )
    kit.supervisor.tick()  # 14:08 passed hours ago: the first trial is due now
    assert kit.sent[-1][1] == "\x1b[200~continue\x1b[201~\r"
    assert session.verify_after is not None
    kit.terminal.set_screen(TAB, list(DIALOG))  # the continuation drew the dialog

    assert kit.supervisor.tick()[0].reason == "verifying"
    kit.clock.advance(10)
    assert kit.supervisor.tick()[0].reason.startswith("verify:")
    assert len(kit.sent) == 1
    kit.clock.advance(1)
    kit.supervisor.tick()
    assert kit.sent[-1] == (TAB, KEEP_MODEL_KEYSTROKES)
