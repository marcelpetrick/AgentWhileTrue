# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Runnable safety scenarios.

Section 40 of the vision lists the situations that must be exercised before the
tool can be trusted, and points out the practical problem: a real quota reset
takes hours, so none of them can be reproduced on demand. These scenarios drive
the whole supervisor against an in-memory terminal and a controllable clock, so
each one runs in milliseconds.

They exist for two audiences. The test suite asserts on them, which is how the
guarantees stay true as the code changes. And ``agent-while-true simulate <name>``
lets a person watch a specific danger play out and read the decisions the
supervisor made, which is a far better way to gain confidence in a tool that
types into terminals than reading its source.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agent_while_true.config import Config, Mode, Policy
from agent_while_true.fsm import APPROVAL_RECHECK_SECONDS, Supervisor
from agent_while_true.logging_setup import setup
from agent_while_true.proc import ProcessIdentity, ProcessInfo
from agent_while_true.quota import Availability, QuotaSnapshot, QuotaSource, QuotaWindow, unknown
from agent_while_true.state_store import StateStore
from agent_while_true.terminal.fake import FakeAdapter

SESSION = "/Sessions/1"
AGENT_PID = 15102
START = datetime(2026, 9, 5, 19, 30, tzinfo=UTC)

CLAUDE_EXE = "/home/user/.local/share/claude/versions/2.1.261"
CODEX_EXE = "/opt/@openai/codex/bin/codex"

BLOCKED_SCREEN = [
    "  ⎿  You've hit your session limit · resets in 5m",
    "",
    "❯ ",
]
BLOCKED_30_SECONDS_SCREEN = [
    "  ⎿  You've hit your session limit · resets in 30s",
    "",
    "❯ ",
]
READY_SCREEN = [
    "● Usage limit has reset · press enter to continue",
    "",
    "❯ ",
]
ACTIVE_SCREEN = ["● Reading src/main.py", "", "❯ "]
SHELL_SCREEN = ["user@host ~/project %"]
UNKNOWN_MENU_SCREEN = [
    "  ⎿  You've hit your session limit · resets in 30s",
    "",
    "   What do you want to do?",
    "",
    "   ❯ 1. Stop and wait for limit to reset",
    "     2. Open an unrecognised recovery mode",
    "     3. Cancel",
    "",
    "   Enter to confirm · Esc to cancel",
]
PAID_CREDITS_SCREEN = [
    "● Usage limit reached · resets in 30s",
    "  Run /extra-usage to continue now",
    "",
    "❯ ",
]
MODEL_DOWNGRADE_SCREEN = [
    "● Usage limit reached · resets in 30s",
    "  Continue now at lower priority",
    "",
    "❯ ",
]
SELF_HEALING_SCREEN = [
    "● Usage limit reached · resets in 5m",
    "  Continuing automatically when your limit resets",
    "❯ ",
]
#: The 2026-09-20 wait menu, verbatim from Claude Code 2.1.278.
WAIT_MENU_SCREEN = [
    "  ⎿  You've hit your session limit · resets in 5m",
    "",
    "   What do you want to do?",
    "",
    "   ❯ 1. Stop and wait for limit to reset",
    "     2. Wait here, then continue automatically shortly",
    "     3. Upgrade your plan",
    "",
    "   Enter to confirm · Esc to cancel",
]
#: What 2.1.278 shows once the wait is armed. It names no time.
ARMED_WAIT_SCREEN = [
    "  ⎿  Claude Code will continue automatically shortly. Keep this session open.",
    "",
    "  ⚠ Usage limit reached · continuing shortly · esc to cancel",
]
CODEX_BLOCKED_SCREEN = ["▌ You've hit your usage limit. Try again at 8:10 PM.", "", "› "]
#: Claude Code's permission box, as read live on 2026-09-28; the command is invented.
_BOX_RULE = "\u2500" * 80
APPROVAL_SCREEN = [
    "● Running the end-to-end suite.",
    "",
    _BOX_RULE,
    " Bash command",
    "",
    "   │ make e2e",
    "   Run shell command",
    "",
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. No",
    "",
    " Esc to cancel · Tab to amend",
]
#: The three-option box with the operator's cursor moved onto item 2.
APPROVAL_CURSOR_MOVED_SCREEN = [
    *APPROVAL_SCREEN[:9],
    "   1. Yes",
    " ❯ 2. Yes, and don't ask again for make commands in /home/user/project",
    "   3. No, and tell Claude what to do differently (esc)",
    "",
    " Esc to cancel · Tab to amend",
]


@dataclass(slots=True)
class Step:
    """One thing that happened, and what the supervisor decided about it."""

    label: str
    decision_reason: str
    sent: int


@dataclass(slots=True)
class Result:
    """The outcome of one scenario."""

    name: str
    description: str
    expectation: str
    passed: bool
    steps: list[Step] = field(default_factory=list)
    sent: list[tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"scenario   {self.name}",
            f"about      {self.description}",
            f"expects    {self.expectation}",
            "",
        ]
        lines.extend(
            f"  {index:>2}. {step.label:<44} -> {step.decision_reason} (sent={step.sent})"
            for index, step in enumerate(self.steps, start=1)
        )
        lines.append("")
        lines.append(f"keystrokes {self.sent or 'none'}")
        lines.append(f"result     {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


# -- the simulated world ---------------------------------------------------


@dataclass(slots=True)
class _Clock:
    wall: datetime = START
    monotonic: float = 1000.0

    def advance(self, seconds: float) -> None:
        self.wall = self.wall.fromtimestamp(self.wall.timestamp() + seconds, tz=UTC)
        self.monotonic += seconds

    def suspend(self, seconds: float) -> None:
        """Wall time passes; the monotonic clock barely moves."""
        self.wall = self.wall.fromtimestamp(self.wall.timestamp() + seconds, tz=UTC)
        self.monotonic += 1.0


@dataclass(slots=True)
class _Processes:
    table: dict[int, ProcessInfo] = field(default_factory=dict)

    def agent(self, pid: int, *, provider: str = "claude", start_time: int = 111) -> ProcessInfo:
        claude = provider == "claude"
        info = ProcessInfo(
            identity=ProcessIdentity(
                pid=pid,
                start_time=start_time,
                tty="pts/3",
                exe=CLAUDE_EXE if claude else CODEX_EXE,
            ),
            ppid=1,
            comm="claude" if claude else "codex",
            cmdline=("claude", "--resume") if claude else (CODEX_EXE, "resume"),
            cwd="/home/user/project",
            environ_keys=frozenset({"HOME"}),
        )
        self.table[pid] = info
        return info

    def shell(self, pid: int) -> ProcessInfo:
        info = ProcessInfo(
            identity=ProcessIdentity(pid=pid, start_time=777, tty="pts/3", exe="/usr/bin/zsh"),
            ppid=1,
            comm="zsh",
            cmdline=("zsh",),
            cwd="/home/user/project",
            environ_keys=frozenset({"HOME"}),
        )
        self.table[pid] = info
        return info

    def inspect(self, pid: int) -> ProcessInfo | None:
        return self.table.get(pid)

    def identify(self, pid: int) -> ProcessIdentity | None:
        info = self.table.get(pid)
        return info.identity if info else None


@dataclass(slots=True)
class _Quota(QuotaSource):
    clock: _Clock
    provider: str = "claude"
    name: str = "simulated"
    availability: Availability = Availability.AVAILABLE
    windows: tuple[QuotaWindow, ...] = ()
    fresh: bool = True

    def snapshot(self, *, pid: int | None = None) -> QuotaSnapshot:
        del pid
        if self.availability is Availability.UNKNOWN:
            return unknown(self.provider, self.name, "simulated-unavailable")
        return QuotaSnapshot(
            provider=self.provider,
            availability=self.availability,
            source=self.name,
            observed_at=self.clock.wall if self.fresh else None,
            windows=self.windows,
        )


@dataclass(slots=True)
class World:
    """Everything a scenario can manipulate."""

    clock: _Clock
    terminal: FakeAdapter
    processes: _Processes
    supervisor: Supervisor
    quota: dict[str, _Quota]
    steps: list[Step] = field(default_factory=list)

    def step(self, label: str) -> None:
        """Advance the supervisor once and record what it decided."""
        decisions = self.supervisor.tick()
        reason = decisions[0].reason if decisions else "no-sessions"
        self.steps.append(Step(label=label, decision_reason=reason, sent=len(self.terminal.sent)))

    def approve(self, label: str) -> None:
        """One scan with the dashboard's auto-yes switched on."""
        self.supervisor.tick()
        outcomes = self.supervisor.approve_pending()
        reason = ", ".join(sorted(outcomes.values())) or "nothing-to-approve"
        self.steps.append(Step(label=label, decision_reason=reason, sent=len(self.terminal.sent)))

    def screen(self, lines: list[str]) -> None:
        self.terminal.set_screen(SESSION, list(lines))


def _world(
    directory: Path,
    *,
    mode: Mode = Mode.AUTO,
    policy: Policy | None = None,
    provider: str = "claude",
    screen: list[str] | None = None,
) -> World:
    clock = _Clock()
    terminal = FakeAdapter()
    processes = _Processes()
    info = processes.agent(AGENT_PID, provider=provider)
    terminal.add(
        SESSION,
        shell_pid=100,
        foreground_pid=AGENT_PID,
        screen=list(screen or BLOCKED_SCREEN),
        title=f"project : {provider}",
    )
    quota = {
        "claude": _Quota(clock=clock, provider="claude"),
        "codex": _Quota(clock=clock, provider="codex"),
    }
    supervisor = Supervisor(
        terminal=terminal,
        config=Config(mode=mode, policy=policy or Policy()),
        store=StateStore.in_directory(directory).load(),
        quota_sources=dict(quota),
        log=setup(directory / "simulate.log"),
        inspector=processes,
        now_fn=lambda: clock.wall,
        monotonic_fn=lambda: clock.monotonic,
        verify_delay=5.0,
    )
    supervisor.select(terminal.ref(SESSION), info.identity, provider, "project")
    return World(
        clock=clock,
        terminal=terminal,
        processes=processes,
        supervisor=supervisor,
        quota=quota,
    )


# -- the scenarios ---------------------------------------------------------

ScenarioFn = Callable[[Path], Result]


def _result(name: str, description: str, expectation: str, world: World, passed: bool) -> Result:
    return Result(
        name=name,
        description=description,
        expectation=expectation,
        passed=passed,
        steps=world.steps,
        sent=list(world.terminal.sent),
    )


def _ready_world(
    directory: Path,
    *,
    mode: Mode = Mode.AUTO,
    blocked_screen: list[str] | None = None,
) -> World:
    """A Claude session seen at its limit, now showing the reset affordance.

    The affordance authorises nothing on a process never seen blocked, so every
    scenario about what happens *at* the ready prompt starts from the limit.
    """
    world = _world(directory, mode=mode, screen=blocked_screen)
    world.step("limit reached, waiting")
    world.supervisor.sessions[world.terminal.ref(SESSION).key()].next_check_at = None
    world.screen(READY_SCREEN)
    return world


def scenario_reset_and_resume(directory: Path) -> Result:
    world = _world(directory, screen=BLOCKED_30_SECONDS_SCREEN)
    world.step("limit reached, waiting")
    world.screen(READY_SCREEN)
    world.clock.advance(30)
    world.step("limit reset, prompt offers to continue")
    world.screen(ACTIVE_SCREEN)
    world.clock.advance(10)
    world.step("verify the session resumed")
    return _result(
        "reset-and-resume",
        "The ordinary happy path: the window resets after 30 seconds and the session continues.",
        "exactly one Enter is sent, and the resume is verified",
        world,
        passed=world.terminal.sent == [(SESSION, "\r")],
    )


def scenario_reset_delayed_90s(directory: Path) -> Result:
    world = _ready_world(directory, blocked_screen=BLOCKED_30_SECONDS_SCREEN)
    world.quota["claude"].availability = Availability.EXHAUSTED
    world.clock.advance(30)
    world.step("nominal reset passes but provider still says exhausted")
    world.clock.advance(90)
    world.quota["claude"].availability = Availability.AVAILABLE
    world.supervisor.sessions[world.terminal.ref(SESSION).key()].next_check_at = None
    world.step("provider confirms availability 90 seconds late")
    return _result(
        "reset-delayed-90s",
        "The provider confirms a reset 90 seconds after the nominal time.",
        "elapsed time sends nothing; fresh availability permits exactly one Enter",
        world,
        passed=world.terminal.sent == [(SESSION, "\r")]
        and world.steps[-2].decision_reason == "usage-not-confirmed-available",
    )


def scenario_prompt_changed_before_send(directory: Path) -> Result:
    world = _ready_world(directory)
    reads = 0

    def change_after_observation(session_id: str) -> None:
        nonlocal reads
        reads += 1
        if reads == 1:
            world.terminal.set_screen(session_id, [*READY_SCREEN, "  changed after observation"])

    world.terminal.after_read = change_after_observation
    world.step("the prompt changes between observation and final revalidation")
    return _result(
        "prompt-changed-before-send",
        "The visible prompt changes in the narrow interval before sendText.",
        "the fingerprint mismatch cancels the action and sends nothing",
        world,
        passed=world.terminal.sent == []
        and world.steps[-1].decision_reason == "revalidation-failed:prompt-changed",
    )


def scenario_terminal_closed(directory: Path) -> Result:
    world = _ready_world(directory)
    world.terminal.close(SESSION)
    world.step("the selected terminal closes before its action")
    world.supervisor.prune_and_rebind()
    return _result(
        "terminal-closed",
        "The selected Konsole tab disappears before the scheduled action.",
        "nothing is typed and rediscovery removes the dead selection",
        world,
        passed=world.terminal.sent == [] and world.supervisor.sessions == {},
    )


def scenario_process_restarted(directory: Path) -> Result:
    world = _ready_world(directory)
    replacement = world.processes.agent(AGENT_PID + 1, start_time=222)
    world.terminal.set_foreground(SESSION, replacement.identity.pid)
    world.step("the agent restarts in the same Konsole tab")
    return _result(
        "process-restarted",
        "A new agent process replaces the selected one in the same tab.",
        "the selection stays bound to the old identity and sends nothing",
        world,
        passed=world.terminal.sent == [] and "process" in world.steps[-1].decision_reason,
    )


def scenario_session_replaced(directory: Path) -> Result:
    world = _ready_world(directory)
    world.terminal.service = "fake.service-2"
    world.supervisor.prune_and_rebind()
    world.step("Konsole reuses the session path under a new service")
    return _result(
        "session-replaced",
        "A new Konsole process exposes the same visible session path.",
        "the service-bound selection is removed and never transferred",
        world,
        passed=world.terminal.sent == [] and world.supervisor.sessions == {},
    )


def scenario_continue_still_blocked(directory: Path) -> Result:
    world = _ready_world(directory)
    world.step("the tested continuation is sent")
    world.clock.advance(5)
    world.step("the unchanged prompt proves the continuation did not land")
    session = world.supervisor.sessions[world.terminal.ref(SESSION).key()]
    retry_at = session.next_check_at
    world.clock.advance(1)
    world.step("a scan before the retry deadline remains silent")
    return _result(
        "continue-still-blocked",
        "A supported continuation is sent but the blocking prompt remains.",
        "the failure is recorded and no immediate duplicate is sent",
        world,
        passed=world.terminal.sent == [(SESSION, "\r")]
        and world.steps[-2].decision_reason == "verify:still-blocked"
        and retry_at is not None
        and retry_at > world.clock.wall,
    )


def scenario_unknown_menu(directory: Path) -> Result:
    world = _world(directory, screen=UNKNOWN_MENU_SCREEN)
    world.step("an unrecognised limit menu is displayed")
    return _result(
        "unknown-menu",
        "A limit menu differs from every tested safe shape.",
        "the unknown layout is observed but never answered",
        world,
        passed=world.terminal.sent == []
        and world.steps[-1].decision_reason == "no-unambiguous-action-for-prompt",
    )


def scenario_paid_credits_prompt(directory: Path) -> Result:
    world = _world(directory, screen=PAID_CREDITS_SCREEN)
    world.step("Claude offers paid extra usage")
    return _result(
        "paid-credits-prompt",
        "Claude offers a paid path around the usage limit.",
        "the paid action is vetoed and no input is sent",
        world,
        passed=world.terminal.sent == []
        and world.steps[-1].decision_reason.startswith("paid-action-required:"),
    )


def scenario_model_downgrade_prompt(directory: Path) -> Result:
    world = _world(directory, screen=MODEL_DOWNGRADE_SCREEN)
    world.step("Claude offers lower-priority service")
    return _result(
        "model-downgrade-prompt",
        "Claude offers continuation with reduced service quality.",
        "the quality-changing action is vetoed and no input is sent",
        world,
        passed=world.terminal.sent == []
        and world.steps[-1].decision_reason.startswith("model-downgrade-offer:"),
    )


def scenario_agent_exited(directory: Path) -> Result:
    world = _world(directory)
    world.step("limit reached, waiting")
    world.processes.shell(AGENT_PID + 1)
    world.terminal.set_foreground(SESSION, AGENT_PID + 1)
    world.screen(SHELL_SCREEN)
    world.clock.advance(300)
    world.step("agent exited; zsh now has the foreground")
    return _result(
        "agent-exited",
        "DANGER 2: the agent exits and a shell takes the foreground before the reset.",
        "nothing is typed, because typing here would run a command in zsh",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_pid_reused(directory: Path) -> Result:
    world = _world(directory, screen=READY_SCREEN)
    world.processes.agent(AGENT_PID, start_time=999999)
    world.step("same PID, different process")
    return _result(
        "pid-reused",
        "DANGER 1: the PID is recycled by an unrelated process.",
        "the identity mismatch is caught and nothing is typed",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_suspend_across_reset(directory: Path) -> Result:
    world = _world(directory)
    world.step("limit reached, reset scheduled")
    world.clock.suspend(6 * 3600)
    world.processes.shell(AGENT_PID + 2)
    world.terminal.set_foreground(SESSION, AGENT_PID + 2)
    world.screen(SHELL_SCREEN)
    world.step("laptop wakes six hours later; the agent is long gone")
    return _result(
        "suspend-across-reset",
        "DANGER 9: the machine sleeps through the reset and wakes much later.",
        "the stale schedule is discarded and nothing is replayed",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_stale_banner(directory: Path) -> Result:
    stale = [*READY_SCREEN, *[f"  build output line {n}" for n in range(60)], "❯ "]
    world = _world(directory, screen=stale)
    world.step("an old reset banner has scrolled far up the screen")
    return _result(
        "stale-banner",
        "DANGER 3: a limit message that is visible history, not the current state.",
        "the scrolled-away banner cannot trigger anything",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_weekly_limit_still_blocked(directory: Path) -> Result:
    world = _ready_world(directory)
    world.quota["claude"].availability = Availability.EXHAUSTED
    world.quota["claude"].windows = (
        QuotaWindow("session", 4.0, None),
        QuotaWindow("weekly", 100.0, START),
    )
    world.step("five-hour window reset, weekly window still spent")
    return _result(
        "weekly-limit-still-blocked",
        "Vision section 25: one window resets while another is still exhausted.",
        "the still-spent weekly limit prevents the resume",
        world,
        passed=world.terminal.sent == []
        and world.steps[-1].decision_reason.startswith("other-limit-still-exhausted"),
    )


def scenario_provider_unavailable(directory: Path) -> Result:
    world = _world(directory)
    world.quota["claude"].availability = Availability.UNKNOWN
    world.step("limit reached; the quota source is unavailable")
    world.clock.advance(3600)
    world.step("well past the nominal reset, still no provider state")
    return _result(
        "provider-unavailable",
        "DANGER 19: the quota source is down when the reset time passes.",
        "auto mode fails closed rather than inferring that usage returned",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_self_healing_provider(directory: Path) -> Result:
    world = _world(directory, screen=SELF_HEALING_SCREEN)
    world.step("Claude says it will continue automatically")
    world.clock.advance(600)
    world.step("after the reset")
    return _result(
        "self-healing-provider",
        "Claude Code 2.1.234+ resumes itself and says so on screen.",
        "the supervisor stands down instead of racing the provider",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_wait_menu_gauge_says_available(directory: Path) -> Result:
    world = _world(directory, screen=WAIT_MENU_SCREEN)
    world.quota["claude"].availability = Availability.AVAILABLE
    world.quota["claude"].windows = (QuotaWindow("session", 99.0, None),)
    world.step("the wait menu is up while the gauge still reads 99 %")
    world.screen(ARMED_WAIT_SCREEN)
    world.clock.advance(10)
    world.step("verify Claude took over the waiting")
    return _result(
        "wait-menu-gauge-says-available",
        "Claude's status line caps at 99 %, so the gauge never says exhausted.",
        "the banner above the menu arms Claude's own wait, and nothing paid is touched",
        world,
        passed=world.terminal.sent == [(SESSION, "\x1b[B\r")],
    )


def scenario_armed_wait_is_left_alone(directory: Path) -> Result:
    world = _world(directory, screen=ARMED_WAIT_SCREEN)
    world.quota["claude"].availability = Availability.EXHAUSTED
    world.step("Claude is already waiting by itself, without naming a time")
    world.clock.advance(600)
    world.step("after the reset")
    return _result(
        "armed-wait-is-left-alone",
        "2.1.278 announces an armed wait without naming a time.",
        "the supervisor stands down instead of racing the provider",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_duplicate_prompt(directory: Path) -> Result:
    world = _ready_world(directory)
    world.step("ready prompt seen")
    for index in range(4):
        world.clock.advance(1)
        world.step(f"same prompt scanned again ({index + 1})")
    return _result(
        "duplicate-prompt",
        "DANGER 17: the same screen is scanned many times over.",
        "one logical prompt yields exactly one keystroke",
        world,
        passed=world.terminal.sent == [(SESSION, "\r")],
    )


def scenario_crash_between_send_and_persist(directory: Path) -> Result:
    world = _ready_world(directory)
    world.step("ready prompt; the action is planned, sent and recorded")

    # Simulate a crash and restart: a brand new supervisor over the same state
    # directory and the same unchanged screen.
    restarted = _ready_world(directory)
    restarted.processes.agent(AGENT_PID)
    restarted.step("after restart, the same prompt is still on screen")
    combined = World(
        clock=restarted.clock,
        terminal=restarted.terminal,
        processes=restarted.processes,
        supervisor=restarted.supervisor,
        quota=restarted.quota,
        steps=world.steps + restarted.steps,
    )
    return _result(
        "crash-recovery",
        "DANGER 13: the supervisor restarts with the same prompt still displayed.",
        "the persisted record prevents a second keystroke",
        combined,
        passed=restarted.terminal.sent == []
        and restarted.steps[-1].decision_reason == "already-actioned",
    )


def scenario_codex_needs_opt_in(directory: Path) -> Result:
    world = _world(directory, provider="codex", screen=CODEX_BLOCKED_SCREEN)
    world.step("Codex is blocked and its window has reset")
    return _result(
        "codex-needs-opt-in",
        "Codex resume means typing into the composer, not pressing Enter.",
        "nothing is typed until the user opts in explicitly",
        world,
        passed=world.terminal.sent == [],
    )


def scenario_observe_mode(directory: Path) -> Result:
    world = _ready_world(directory, mode=Mode.OBSERVE)
    world.step("ready prompt in observe mode")
    return _result(
        "observe-mode",
        "Observe mode runs the whole detection path.",
        "the decision is reached but no input is ever sent",
        world,
        passed=world.terminal.sent == [] and world.steps[-1].decision_reason == "observe-mode",
    )


def scenario_approval_waits_for_the_operator(directory: Path) -> Result:
    world = _world(directory, screen=APPROVAL_SCREEN)
    for index in range(3):
        world.step(f"Claude asks to run a command ({index + 1})")
        world.clock.advance(5)
    return _result(
        "approval-waits-for-operator",
        "Full auto sees Claude Code ask for permission to run a tool.",
        "without the auto-yes switch nothing is approved, however long it waits",
        world,
        passed=world.terminal.sent == []
        and all(step.decision_reason.endswith("APPROVAL_PENDING") for step in world.steps),
    )


def scenario_auto_yes_answers_once(directory: Path) -> Result:
    world = _world(directory, screen=APPROVAL_CURSOR_MOVED_SCREEN)
    world.approve("the cursor was moved off Yes")
    world.screen(APPROVAL_SCREEN)
    world.approve("exact permission menu, auto-yes on")
    world.approve("the same box, Claude has not redrawn yet")
    world.screen(ACTIVE_SCREEN)
    world.approve("the command runs")
    world.screen(APPROVAL_SCREEN)
    world.supervisor.tick()
    world.screen([line.replace("make e2e", "rm -rf ~") for line in APPROVAL_SCREEN])
    outcomes = world.supervisor.approve_pending()
    world.steps.append(
        Step(
            label="the command changed after the scan",
            decision_reason=", ".join(outcomes.values()),
            sent=len(world.terminal.sent),
        )
    )
    return _result(
        "auto-yes-answers-once",
        "The operator switched auto-yes on; Claude Code asks for permission.",
        "only an exact permission menu is answered, once, and a changed box is refused",
        world,
        passed=world.terminal.sent == [(SESSION, "\r")]
        and outcomes == {world.terminal.ref(SESSION).key(): "prompt-changed"},
    )


def scenario_auto_yes_resends_once(directory: Path) -> Result:
    world = _world(directory, screen=APPROVAL_SCREEN)
    world.approve("exact permission menu, auto-yes on")
    world.clock.advance(APPROVAL_RECHECK_SECONDS - 1)
    world.approve("the same box, still inside the settle delay")
    world.clock.advance(1)
    world.approve("the same box outlived its Enter")
    world.clock.advance(APPROVAL_RECHECK_SECONDS)
    world.approve("the same box outlived the second Enter as well")
    for index in range(2):
        world.clock.advance(APPROVAL_RECHECK_SECONDS)
        world.approve(f"the operator has not answered yet ({index + 1})")
    return _result(
        "auto-yes-resends-once",
        "Auto-yes answered a permission menu, but the identical box stays on screen.",
        "one more Enter after the settle delay, then it is reported once and left alone",
        world,
        passed=world.terminal.sent == [(SESSION, "\r"), (SESSION, "\r")]
        and [step.decision_reason for step in world.steps]
        == [
            "approved",
            "nothing-to-approve",
            "resent",
            "unanswered-after-resend",
            "nothing-to-approve",
            "nothing-to-approve",
        ],
    )


SCENARIOS: dict[str, ScenarioFn] = {
    "reset-and-resume": scenario_reset_and_resume,
    "reset-delayed-90s": scenario_reset_delayed_90s,
    "prompt-changed-before-send": scenario_prompt_changed_before_send,
    "terminal-closed": scenario_terminal_closed,
    "process-restarted": scenario_process_restarted,
    "session-replaced": scenario_session_replaced,
    "continue-still-blocked": scenario_continue_still_blocked,
    "unknown-menu": scenario_unknown_menu,
    "paid-credits-prompt": scenario_paid_credits_prompt,
    "model-downgrade-prompt": scenario_model_downgrade_prompt,
    "agent-exited": scenario_agent_exited,
    "pid-reused": scenario_pid_reused,
    "suspend-across-reset": scenario_suspend_across_reset,
    "stale-banner": scenario_stale_banner,
    "weekly-limit-still-blocked": scenario_weekly_limit_still_blocked,
    "provider-unavailable": scenario_provider_unavailable,
    "self-healing-provider": scenario_self_healing_provider,
    "wait-menu-gauge-says-available": scenario_wait_menu_gauge_says_available,
    "armed-wait-is-left-alone": scenario_armed_wait_is_left_alone,
    "duplicate-prompt": scenario_duplicate_prompt,
    "crash-recovery": scenario_crash_between_send_and_persist,
    "codex-needs-opt-in": scenario_codex_needs_opt_in,
    "observe-mode": scenario_observe_mode,
    "approval-waits-for-operator": scenario_approval_waits_for_the_operator,
    "auto-yes-answers-once": scenario_auto_yes_answers_once,
    "auto-yes-resends-once": scenario_auto_yes_resends_once,
}


def catalogue() -> list[tuple[str, str]]:
    """Every scenario name with its one-line description."""
    with tempfile.TemporaryDirectory() as directory:
        return [(name, run(name, Path(directory)).description) for name in SCENARIOS]


def run(name: str, directory: Path | None = None) -> Result:
    """Run one scenario. Raises ``KeyError`` for an unknown name."""
    scenario = SCENARIOS[name]
    if directory is not None:
        return scenario(directory / name)
    with tempfile.TemporaryDirectory() as temporary:
        return scenario(Path(temporary))


def run_all(directory: Path | None = None) -> list[Result]:
    return [run(name, directory) for name in SCENARIOS]


__all__ = ["SCENARIOS", "Result", "Step", "catalogue", "run", "run_all"]
