# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The supervisor: one tick of observe, decide, act, verify.

This module wires together everything the other modules provide and owns the
per-session state machine from section 27 of the vision. Three of its
responsibilities are load-bearing and worth naming.

**Revalidation before input.** :meth:`Supervisor.act` does not trust the
observation the decision was made from. It re-reads the foreground process, the
identity, the session reference and the screen, re-runs the recognizer and
re-runs the gate, and cancels on any drift. The window between deciding and
typing is exactly where "codex exited and zsh took the foreground" lives
(DANGER 2).

**Verification is a state, not a sleep.** After sending, the session moves to
``VERIFYING`` with a deadline. The next tick that passes the deadline re-reads
the screen and settles the action. Nothing blocks, so one wedged session cannot
stall the others.

**Suspend and clock changes.** Retry and grace intervals are measured on the
monotonic clock while reset instants are wall-clock. When the two disagree by
more than a threshold across a tick, the machine was suspended or the clock was
corrected; every pending schedule is discarded and every session is
revalidated from scratch (DANGER 9 and 10).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from agent_watch import providers as provider_registry
from agent_watch.classify import Classification, Confidence, ProcessClass, classify
from agent_watch.config import Config, Mode
from agent_watch.logging_setup import EventLogger, get_logger
from agent_watch.policy import Decision, ResumeRequest, evaluate
from agent_watch.proc import ProcessGoneError, ProcessIdentity, ProcessInfo
from agent_watch.proc import identify as proc_identify
from agent_watch.proc import inspect as proc_inspect
from agent_watch.providers.base import PromptKind, ProviderAdapter, Recognition
from agent_watch.providers.timeparse import parse_reset
from agent_watch.quota import QuotaSnapshot, QuotaSource, unknown
from agent_watch.state_store import StateStore
from agent_watch.states import ActionState, SessionState
from agent_watch.terminal.base import SessionRef, TerminalAdapter, TerminalError

#: A wall-clock/monotonic divergence above this many seconds across one tick is
#: read as suspend/resume or a clock correction rather than as elapsed time.
TIME_JUMP_THRESHOLD_SECONDS = 30.0

#: How long after sending input to check whether it worked.
DEFAULT_VERIFY_DELAY_SECONDS = 5.0

_NOT_AN_AGENT = Classification(ProcessClass.UNKNOWN, Confidence.NONE, (), blocker="process-gone")


class ProcessInspector(Protocol):
    """Reads process facts. Injectable so the loop is testable without /proc."""

    def inspect(self, pid: int) -> ProcessInfo | None: ...

    def identify(self, pid: int) -> ProcessIdentity | None: ...


class SystemInspector:
    """The real ``/proc``-backed inspector."""

    def inspect(self, pid: int) -> ProcessInfo | None:
        try:
            return proc_inspect(pid)
        except (ProcessGoneError, OSError):
            return None

    def identify(self, pid: int) -> ProcessIdentity | None:
        try:
            return proc_identify(pid)
        except (ProcessGoneError, OSError):
            return None


@dataclass(frozen=True, slots=True)
class Observation:
    """One reading of one session at one instant."""

    ref: SessionRef
    at: datetime
    foreground_pid: int
    identity: ProcessIdentity | None
    info: ProcessInfo | None
    classification: Classification
    provider: ProviderAdapter | None
    recognition: Recognition | None
    quota: QuotaSnapshot

    @property
    def is_agent(self) -> bool:
        return self.provider is not None


@dataclass(slots=True)
class SupervisedSession:
    """A session the user selected, plus everything remembered about it."""

    ref: SessionRef
    identity: ProcessIdentity
    provider_name: str
    title: str = ""
    account_label: str = "unavailable"
    state: SessionState = SessionState.DISCOVERED
    reset_at: datetime | None = None
    next_check_at: datetime | None = None
    unsafe_reason: str | None = None
    last_reason: str = ""
    decision_at: datetime | None = None
    observed_at: datetime | None = None
    observed_state: str = "not observed"
    matched_ids: tuple[str, ...] = ()
    reported_refusal: str = ""
    last_fingerprint: str = ""
    pending_key: str = ""
    reset_prompt_key: str = ""
    reset_first_seen: datetime | None = None
    retry_episode_key: str = ""
    verify_after: datetime | None = None
    #: Sends since the last verified resume. The store counts attempts per
    #: prompt; this counts them per session, so a screen that keeps changing
    #: cannot mint a fresh attempt budget on every tick.
    attempts_since_success: int = 0
    quota: QuotaSnapshot = field(
        default_factory=lambda: unknown("unknown", "none", "not-observed-yet")
    )

    @property
    def marked_unsafe(self) -> bool:
        return self.unsafe_reason is not None

    def describe_process(self) -> str:
        return self.identity.key()

    def display_title(self) -> str:
        """Use the classified provider instead of a launcher's process name."""
        title = self.title or self.ref.session_id
        head, separator, tail = title.rpartition(":")
        if separator and tail.strip().lower() in {"node", "codex", "claude"}:
            return f"{head.rstrip()} : {self.provider_name.title()}"
        return title


ConfirmCallback = Callable[[Observation, Decision], bool]


@dataclass(slots=True)
class Supervisor:
    """Owns the supervised sessions and advances them one tick at a time."""

    terminal: TerminalAdapter
    config: Config
    store: StateStore
    quota_sources: dict[str, QuotaSource]
    log: EventLogger = field(default_factory=get_logger)
    inspector: ProcessInspector = field(default_factory=SystemInspector)
    confirm: ConfirmCallback | None = None
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC)
    monotonic_fn: Callable[[], float] = None  # type: ignore[assignment]
    verify_delay: float = DEFAULT_VERIFY_DELAY_SECONDS

    sessions: dict[str, SupervisedSession] = field(default_factory=dict)
    _last_wall: datetime | None = None
    _last_monotonic: float | None = None

    def __post_init__(self) -> None:
        if self.monotonic_fn is None:
            import time

            self.monotonic_fn = time.monotonic

    # -- selection ---------------------------------------------------------

    def select(
        self,
        ref: SessionRef,
        identity: ProcessIdentity,
        provider: str,
        title: str,
        account_label: str = "unavailable",
    ) -> None:
        """Bind a user selection to a concrete identity.

        The binding is to the identity, never to the tab's numeric label, so a
        tab that closes and is later recreated with the same number does not
        inherit the selection (vision DANGER 20).
        """
        self.sessions[ref.key()] = SupervisedSession(
            ref=ref,
            identity=identity,
            provider_name=provider,
            title=title,
            account_label=account_label,
        )
        self.log.info(
            "session_selected",
            provider=provider,
            session=ref.key(),
            pid=identity.pid,
            process=identity.key(),
            tty=identity.tty,
        )

    def deselect(self, key: str) -> None:
        self.sessions.pop(key, None)

    # -- observation -------------------------------------------------------

    def observe(self, ref: SessionRef, *, now: datetime | None = None) -> Observation:
        """Read everything about one session, without deciding anything."""
        moment = now or self.now_fn()
        try:
            foreground_pid = self.terminal.foreground_pid(ref)
        except TerminalError:
            foreground_pid = 0
        if foreground_pid <= 0:
            return Observation(
                ref=ref,
                at=moment,
                foreground_pid=0,
                identity=None,
                info=None,
                classification=_NOT_AN_AGENT,
                provider=None,
                recognition=None,
                quota=unknown("unknown", "none", "session-gone"),
            )

        info = self.inspector.inspect(foreground_pid)
        if info is None:
            return Observation(
                ref=ref,
                at=moment,
                foreground_pid=foreground_pid,
                identity=None,
                info=None,
                classification=_NOT_AN_AGENT,
                provider=None,
                recognition=None,
                quota=unknown("unknown", "none", "process-gone"),
            )

        classification = classify(info)
        provider = provider_registry.for_process_class(classification.process_class)
        recognition = None
        if provider is not None:
            try:
                lines = self.terminal.read_visible_text(ref, self.config.visible_lines)
            except TerminalError:
                lines = []
            recognition = provider.recognise(lines, now=moment)

        return Observation(
            ref=ref,
            at=moment,
            foreground_pid=foreground_pid,
            identity=info.identity,
            info=info,
            classification=classification,
            provider=provider,
            recognition=recognition,
            quota=self._quota(provider, foreground_pid),
        )

    def _quota(self, provider: ProviderAdapter | None, pid: int) -> QuotaSnapshot:
        if provider is None:
            return unknown("unknown", "none", "not-an-agent")
        source = self.quota_sources.get(provider.name)
        if source is None:
            return unknown(provider.name, "none", "no-source-configured")
        return source.snapshot(pid=pid)

    # -- the tick ----------------------------------------------------------

    def tick(self) -> list[Decision]:
        """Advance every supervised session once."""
        now = self.now_fn()
        if self._detect_time_jump(now):
            self._invalidate_schedules(now)
        self._warm_quota_sources()
        decisions = []
        for session in list(self.sessions.values()):
            decision = self._advance(session, now)
            session.last_reason = decision.reason
            session.decision_at = now
            # Count refusal episodes, not every poll of the same blocked prompt.
            refusal = (
                decision.reason
                if not decision.allowed
                and decision.reason
                not in {
                    "verifying",
                    "waiting-for-reset",
                    "declined-by-user",
                    "send-failed",
                }
                and not decision.reason.startswith(("revalidation-failed:", "verify:"))
                and session.observed_state not in {"ACTIVE", "LIMIT_WARNING"}
                else ""
            )
            if refusal and refusal != session.reported_refusal:
                self.log.info(
                    "resume_refused",
                    provider=session.provider_name,
                    reason=refusal,
                    session=session.ref.key(),
                    process=session.describe_process(),
                    episode=session.retry_episode_key,
                    attempt=self._retry_attempt(session),
                )
            session.reported_refusal = refusal
            decisions.append(decision)
        return decisions

    def _warm_quota_sources(self) -> None:
        """Observe every selected account before any session decision is made."""
        for session in self.sessions.values():
            source = self.quota_sources.get(session.provider_name)
            if source is None:
                continue
            # This warm-up only populates account-bound quota caches. The live
            # foreground PID is independently re-read by observe() before any
            # decision, and again immediately before an action.
            source.snapshot(pid=session.identity.pid)

    def _detect_time_jump(self, now: datetime) -> bool:
        monotonic = self.monotonic_fn()
        previous_wall, previous_monotonic = self._last_wall, self._last_monotonic
        self._last_wall, self._last_monotonic = now, monotonic
        if previous_wall is None or previous_monotonic is None:
            return False
        wall_elapsed = (now - previous_wall).total_seconds()
        monotonic_elapsed = monotonic - previous_monotonic
        return abs(wall_elapsed - monotonic_elapsed) > TIME_JUMP_THRESHOLD_SECONDS

    def _invalidate_schedules(self, now: datetime) -> None:
        """Throw away every pending schedule after a suspend or clock change."""
        for session in self.sessions.values():
            session.next_check_at = None
            session.verify_after = None
            if session.state is SessionState.CONTINUE_SENT:
                session.state = SessionState.VERIFYING
        self.log.warning("time_jump_detected", sessions=len(self.sessions), at=now)

    def _advance(self, session: SupervisedSession, now: datetime) -> Decision:
        if session.verify_after is not None:
            if now < session.verify_after:
                return self._skip(session, "verifying")
            return self._verify(session, now)

        previous_deadline = session.next_check_at
        observation = self._anchor_reset(session, self.observe(session.ref, now=now))
        if (
            observation.identity == session.identity
            and observation.recognition is not None
            and observation.recognition.provider == "codex"
            and observation.recognition.state in {SessionState.ACTIVE, SessionState.LIMIT_WARNING}
            and observation.recognition.active_evidence
        ):
            self._finish_episode(session)
        self._prepare_retry(session, observation)
        episode = self.store.get_episode(session.retry_episode_key)
        if episode and episode.pending_key:
            pending = self.store.records.get(episode.pending_key)
            if pending is not None and pending.state is ActionState.SENT:
                session.pending_key = pending.key
                return self._verify(session, now)
        decision = self._decide(session, observation)
        # Waiting gates input, never observation. New/manual activity is always
        # reflected even when a provider reset is hours away.
        if (
            not episode
            and previous_deadline is not None
            and now < previous_deadline
            and decision.allowed
            and observation.recognition is not None
            and observation.recognition.screen_fingerprint == session.last_fingerprint
        ):
            decision = replace(
                decision, allowed=False, reason="waiting-for-reset", retry_at=previous_deadline
            )
        self._record_state(session, observation, decision)

        if not decision.allowed:
            return decision
        if decision.requires_confirmation and not self._confirmed(observation, decision):
            self.log.info(
                "resume_declined_by_user",
                provider=session.provider_name,
                session=session.ref.key(),
                process=session.describe_process(),
            )
            return Decision(allowed=False, reason="declined-by-user", action=decision.action)

        return self.act(session, observation, decision)

    def _skip(self, session: SupervisedSession, reason: str) -> Decision:
        return Decision(allowed=False, reason=reason, retry_at=session.next_check_at)

    def _confirmed(self, observation: Observation, decision: Decision) -> bool:
        if self.confirm is None:
            # Ask mode with no way to ask is not permission; it is a refusal.
            return False
        return self.confirm(observation, decision)

    def _decide(self, session: SupervisedSession, observation: Observation) -> Decision:
        if observation.recognition is None or observation.provider is None:
            reason = (
                "process-gone"
                if observation.identity is None
                else f"not-automatable:{observation.classification.blocker or 'unknown'}"
            )
            return Decision(allowed=False, reason=reason)
        decision = evaluate(self._request(session, observation))
        episode = self.store.get_episode(session.retry_episode_key)
        if episode and observation.identity == session.identity:
            if episode.pending_key:
                return Decision(allowed=False, reason="retry-attempt-unsettled")
            if episode.exhausted or episode.completed:
                return Decision(allowed=False, reason="retry-budget-exhausted")
            if episode.next_retry_at:
                due = datetime.fromisoformat(episode.next_retry_at)
                if observation.at < due and decision.allowed:
                    return replace(
                        decision, allowed=False, reason="waiting-for-reset", retry_at=due
                    )
        return decision

    def _retry_attempt(self, session: SupervisedSession) -> str:
        episode = self.store.get_episode(session.retry_episode_key)
        return f"{episode.attempts if episode else 0}/{len(self.config.retry_schedule)}"

    def _anchor_reset(self, session: SupervisedSession, observation: Observation) -> Observation:
        recognition = observation.recognition
        if (
            recognition is None
            or recognition.provider != "codex"
            or observation.identity != session.identity
        ):
            return observation
        if recognition.reset_at is None:
            return observation
        texts = sorted(
            {
                " ".join(
                    (
                        match.line if parse_reset(match.line, observation.at) else match.context
                    ).split()
                )
                for match in recognition.matches
                if match.id == "codex/try-again-at"
            }
        )
        if not texts:
            return observation
        hint = hashlib.sha256(json.dumps(texts).encode()).hexdigest()
        saved = self.store.find_episode(
            provider="codex",
            session=session.ref.key(),
            process=session.describe_process(),
            prompt_key=hint,
        )
        if hint == session.reset_prompt_key and session.reset_at is not None:
            reset = session.reset_at
        elif saved is not None:
            reset = datetime.fromisoformat(saved.reset_at)
            session.reset_first_seen = datetime.fromisoformat(saved.first_seen_at)
        else:
            reference = session.reset_first_seen or observation.at
            if session.reset_first_seen is None:
                # Absolute window timestamps can date a prompt on restart.
                # Even stale evidence may anchor a date, never availability.
                dated = [
                    window.resets_at
                    for window in observation.quota.windows
                    if window.resets_at is not None
                    and abs((observation.at - window.resets_at).total_seconds()) <= 86400
                    and all(
                        parse_reset(
                            text,
                            window.resets_at.replace(second=0, microsecond=0)
                            - timedelta(seconds=1),
                        )
                        == window.resets_at.replace(second=0, microsecond=0)
                        for text in texts
                    )
                ]
                if dated:
                    reference = max(dated).replace(second=0, microsecond=0) - timedelta(seconds=1)
            parsed = [
                value for text in texts if (value := parse_reset(text, reference)) is not None
            ]
            if not parsed:
                return observation
            reset = max(parsed)
            session.reset_first_seen = reference
            session.retry_episode_key = ""
        session.reset_prompt_key = hint
        session.reset_at = reset
        return replace(observation, recognition=replace(recognition, reset_at=reset))

    def _finish_episode(self, session: SupervisedSession) -> None:
        if session.retry_episode_key and self.config.mode is Mode.AUTO:
            self.store.update_episode(
                session.retry_episode_key, completed=True, pending_key="", next_retry_at=""
            )
        session.retry_episode_key = ""
        session.reset_prompt_key = ""
        session.reset_first_seen = None
        session.reset_at = None
        session.next_check_at = None

    def _prepare_retry(self, session: SupervisedSession, observation: Observation) -> None:
        recognition = observation.recognition
        if not (
            self.config.mode is Mode.AUTO
            and self.config.policy.allow_codex_auto_resume
            and recognition is not None
            and recognition.retry_prompt
            and recognition.reset_at is not None
            and session.reset_first_seen is not None
            and observation.identity == session.identity
            and self.store.retry_state_valid
        ):
            return
        key = hashlib.sha256(
            json.dumps(
                [
                    "codex",
                    session.ref.key(),
                    session.describe_process(),
                    recognition.reset_at.isoformat(),
                ]
            ).encode()
        ).hexdigest()
        episode = self.store.ensure_episode(
            key,
            provider="codex",
            session=session.ref.key(),
            process=session.describe_process(),
            prompt_key=session.reset_prompt_key,
            reset_at=recognition.reset_at.isoformat(),
            first_seen_at=session.reset_first_seen.isoformat(),
        )
        session.retry_episode_key = key
        if not episode.next_retry_at and not episode.attempts and not episode.completed:
            due = recognition.reset_at + timedelta(seconds=self.config.retry_schedule[0])
            self.store.update_episode(key, next_retry_at=due.isoformat())
            self.log.info(
                "resume_retry_scheduled",
                provider="codex",
                session=session.ref.key(),
                process=session.describe_process(),
                episode=key,
                attempt=f"1/{len(self.config.retry_schedule)}",
                due_at=due,
                delay=self.config.retry_schedule[0],
            )

    def _request(self, session: SupervisedSession, observation: Observation) -> ResumeRequest:
        # _decide has already established that a recognition exists.
        recognition = observation.recognition
        if recognition is None:  # pragma: no cover - unreachable via _decide
            raise ValueError("cannot build a resume request without a recognition")
        episode = self.store.get_episode(session.retry_episode_key)
        timed = (
            self.config.mode is Mode.AUTO
            and self.config.policy.allow_codex_auto_resume
            and recognition.provider == "codex"
            and recognition.retry_prompt
            and recognition.reset_at is not None
        )
        return ResumeRequest(
            now=observation.at,
            config=self.config,
            selected=True,
            selected_ref=session.ref,
            live_ref=observation.ref,
            selected_identity=session.identity,
            live_identity=observation.identity,
            classification=observation.classification,
            recognition=recognition,
            quota=observation.quota,
            attempts=episode.attempts
            if timed and episode
            else max(
                self.store.attempts_for(session.pending_key) if session.pending_key else 0,
                session.attempts_since_success,
            ),
            actioned_fingerprints=self.store.already_actioned(),
            marked_unsafe=session.marked_unsafe,
            codex_retry=timed,
            retry_state_valid=self.store.retry_state_valid and (not timed or episode is not None),
        )

    def _record_state(
        self, session: SupervisedSession, observation: Observation, decision: Decision
    ) -> None:
        self._remember_observation(session, observation)
        previous = session.state
        if session.marked_unsafe:
            # An unsafe session stays unsafe until a human clears it; a later
            # screen reading must not quietly promote it back.
            session.last_reason = decision.reason
            session.next_check_at = decision.retry_at
            return
        if observation.identity is None:
            session.state = SessionState.PROCESS_GONE
        elif observation.classification.blocker in {
            "nested-terminal-ancestor=tmux",
            "ssh-environment-marker",
            "ssh-foreground-process",
            "container-cgroup",
        }:
            session.state = SessionState.UNSUPPORTED
        elif observation.recognition is not None:
            session.state = observation.recognition.state
            session.reset_at = observation.recognition.reset_at
            session.last_fingerprint = observation.recognition.screen_fingerprint
        session.last_reason = decision.reason
        session.next_check_at = decision.retry_at
        session.quota = observation.quota

        if session.state is not previous:
            self.log.info(
                "state_change",
                provider=session.provider_name,
                session=session.ref.key(),
                previous=previous.value,
                new=session.state.value,
                reset=session.reset_at,
                reason=decision.reason,
                screen=session.last_fingerprint,
            )

    # -- acting ------------------------------------------------------------

    @staticmethod
    def _remember_observation(session: SupervisedSession, observation: Observation) -> None:
        """Keep display evidence only; never retain the screen or process environment."""
        session.observed_at = observation.at
        session.quota = observation.quota
        recognition = observation.recognition
        session.observed_state = recognition.state.value if recognition else "unrecognized"
        session.matched_ids = tuple(recognition.matched_ids) if recognition else ()

    def act(
        self, session: SupervisedSession, observation: Observation, decision: Decision
    ) -> Decision:
        """Send the resume input, after revalidating everything from scratch.

        The decision handed in is treated as a *proposal*. Between observing and
        acting the agent may have exited, the tab may have been reused, or the
        prompt may have changed; all of that is re-read here, and any drift
        cancels the action.
        """
        fresh = self._anchor_reset(session, self.observe(session.ref))
        self._remember_observation(session, fresh)
        recheck = self._decide(session, fresh)
        if not recheck.allowed:
            self.log.warning(
                "resume_cancelled_on_revalidation",
                provider=session.provider_name,
                session=session.ref.key(),
                reason=recheck.reason,
                planned=decision.reason,
                process=session.describe_process(),
                episode=session.retry_episode_key,
                attempt=self._retry_attempt(session),
            )
            return Decision(allowed=False, reason=f"revalidation-failed:{recheck.reason}")
        if recheck.idempotency_key != decision.idempotency_key:
            # The screen changed under us: this is a different prompt now.
            self.log.warning(
                "resume_cancelled_prompt_changed",
                provider=session.provider_name,
                session=session.ref.key(),
                process=session.describe_process(),
                episode=session.retry_episode_key,
                attempt=self._retry_attempt(session),
            )
            return Decision(allowed=False, reason="revalidation-failed:prompt-changed")

        action = recheck.action
        if action is None:  # pragma: no cover - the gate guarantees one
            return Decision(allowed=False, reason="revalidation-failed:no-action")

        key = recheck.idempotency_key
        episode = self.store.get_episode(session.retry_episode_key)
        if episode is not None:
            key = f"{episode.key}-{episode.attempts + 1}"
        session.pending_key = key
        # Persist the intent before sending. If the process dies here, the
        # restart sees PLANNED and refuses rather than typing a second time.
        if episode is not None:
            self.store.plan_episode_attempt(
                episode.key,
                key,
                provider=session.provider_name,
                session=session.ref.key(),
                process=session.describe_process(),
            )
        else:
            self.store.plan(
                key,
                provider=session.provider_name,
                session=session.ref.key(),
                process=session.describe_process(),
            )
        final = self._final_recheck(session, key, recheck, episode is not None)
        if not final.allowed:
            if episode is not None:
                self.store.release_unsent_episode_attempt(episode.key, key, result=final.reason)
                self._schedule_retry(session, self.now_fn())
            else:
                self.store.mark(key, ActionState.FAILED, result=final.reason)
            self.log.warning(
                "resume_cancelled_on_revalidation",
                provider=session.provider_name,
                session=session.ref.key(),
                process=session.describe_process(),
                episode=session.retry_episode_key,
                attempt=self._retry_attempt(session),
                reason=final.reason,
            )
            return Decision(allowed=False, reason=f"revalidation-failed:{final.reason}")
        try:
            self.terminal.send_text(session.ref, action.keystrokes())
        except TerminalError as exc:
            self.store.mark(key, ActionState.FAILED, result=f"send-failed:{type(exc).__name__}")
            session.state = SessionState.LIMIT_BLOCKED
            self.log.error(
                "resume_send_failed",
                provider=session.provider_name,
                session=session.ref.key(),
                error=type(exc).__name__,
                process=session.describe_process(),
                episode=session.retry_episode_key,
                attempt=self._retry_attempt(session),
            )
            if episode is not None:
                self._schedule_retry(session, fresh.at)
            return Decision(allowed=False, reason="send-failed")

        self.store.mark(key, ActionState.SENT)
        session.attempts_since_success += 1
        session.state = SessionState.CONTINUE_SENT
        session.verify_after = fresh.at + timedelta(
            seconds=min(self.verify_delay, 1) if episode else self.verify_delay
        )
        self.log.info(
            "resume_sent",
            provider=session.provider_name,
            session=session.ref.key(),
            process=session.describe_process(),
            action=action.kind.value,
            authorization=recheck.authorization.value,
            attempt=self._retry_attempt(session) if episode else self.store.attempts_for(key),
            episode=session.retry_episode_key,
            screen=fresh.recognition.screen_fingerprint if fresh.recognition else "",
        )
        return Decision(allowed=True, reason="resume-sent", action=action, idempotency_key=key)

    def _final_recheck(
        self, session: SupervisedSession, key: str, proposal: Decision, reserved: bool
    ) -> Decision:
        """Revalidate after durable writes; the last external read is identity.

        D-Bus cannot atomically compare a screen and send text. Minimize that
        unavoidable boundary: perform no persistence between this check and send.
        """
        fresh = self._anchor_reset(session, self.observe(session.ref))
        self._remember_observation(session, fresh)
        if fresh.recognition is None:
            return Decision(False, "process-gone")
        request = self._request(session, fresh)
        episode = self.store.get_episode(session.retry_episode_key)
        if reserved and episode is not None and episode.next_retry_at:
            due = datetime.fromisoformat(episode.next_retry_at)
            if fresh.at < due:
                return Decision(False, "retry-not-due", retry_at=due)
        # This is verification of our reserved attempt, not a request for a
        # second one. Other persisted action keys remain vetoes.
        request = replace(
            request,
            attempts=max(0, request.attempts - 1) if reserved else request.attempts,
            actioned_fingerprints=request.actioned_fingerprints - {key},
        )
        final = evaluate(request)
        if not final.allowed:
            return final
        if final.idempotency_key != proposal.idempotency_key or final.action != proposal.action:
            return Decision(False, "prompt-changed")
        try:
            live = self.inspector.inspect(self.terminal.foreground_pid(session.ref))
        except (TerminalError, OSError):
            live = None
        if live is None or live.identity != session.identity:
            return Decision(False, "process-identity-changed")
        classification = classify(live)
        if (
            not classification.automatable
            or classification.process_class.value.lower() != session.provider_name
        ):
            return Decision(False, "process-classification-changed")
        return final

    # -- verification ------------------------------------------------------

    def _verify(self, session: SupervisedSession, now: datetime) -> Decision:
        """Decide whether the input actually did anything.

        Sending is not succeeding: the prompt has to go away.
        """
        session.verify_after = None
        observation = self._anchor_reset(session, self.observe(session.ref, now=now))
        key = session.pending_key
        self._remember_observation(session, observation)

        if self.config.mode is Mode.OBSERVE:
            # The input lock has been released. Do not overwrite retry state
            # another controller might now own; verify on reacquiring it.
            return Decision(allowed=False, reason="observe-mode")

        if observation.recognition is None or observation.identity != session.identity:
            # The agent is gone. That is not a failure of the keystroke, but it
            # is certainly not a verified resume either.
            self.store.mark(key, ActionState.FAILED, result="process-gone")
            self.log.warning(
                "resume_verification_failed",
                provider=session.provider_name,
                reason="process-gone",
                session=session.ref.key(),
                process=session.describe_process(),
                episode=session.retry_episode_key,
                attempt=self._retry_attempt(session),
            )
            session.state = SessionState.PROCESS_GONE
            return Decision(allowed=False, reason="verify:process-gone")

        armed_self_resume = any(
            match.pattern.kind is PromptKind.SELF_HEALING
            for match in observation.recognition.matches
        )
        resumed = armed_self_resume or observation.recognition.state in {
            SessionState.ACTIVE,
            SessionState.LIMIT_WARNING,
        }
        if session.retry_episode_key and not observation.recognition.active_evidence:
            resumed = False
        if resumed:
            result = "armed-provider-wait" if armed_self_resume else "resumed"
            self.store.mark(key, ActionState.VERIFIED, result=result)
            session.state = (
                SessionState.WAITING_FOR_RESET
                if armed_self_resume
                else observation.recognition.state
            )
            session.pending_key = ""
            session.attempts_since_success = 0
            self.log.info(
                "resume_verified",
                provider=session.provider_name,
                session=session.ref.key(),
                result=result,
                process=session.describe_process(),
                episode=session.retry_episode_key,
                attempt=self._retry_attempt(session),
            )
            self._finish_episode(session)
            reason = "verify:armed-provider-wait" if armed_self_resume else "resume-verified"
            return Decision(allowed=True, reason=reason)

        attempts = self.store.attempts_for(key)
        self.store.mark(key, ActionState.FAILED, result="still-blocked")
        session.state = observation.recognition.state
        # Back off on the monotonic-derived schedule rather than retrying at
        # once; the wall clock is not trustworthy for short intervals.
        if session.retry_episode_key:
            self._schedule_retry(session, now)
        else:
            session.next_check_at = now + timedelta(seconds=self.config.retry_delay(attempts))
        self.log.warning(
            "resume_not_verified",
            provider=session.provider_name,
            session=session.ref.key(),
            attempt=self._retry_attempt(session) if session.retry_episode_key else attempts,
            state=session.state.value,
            retry_at=session.next_check_at,
            next_retry_at=session.next_check_at,
            process=session.describe_process(),
            episode=session.retry_episode_key,
        )
        return Decision(
            allowed=False, reason="verify:still-blocked", retry_at=session.next_check_at
        )

    def _schedule_retry(self, session: SupervisedSession, now: datetime) -> None:
        episode = self.store.get_episode(session.retry_episode_key)
        if episode is None:
            return
        budget = len(self.config.retry_schedule)
        if episode.attempts >= budget:
            self.store.update_episode(episode.key, exhausted=True, pending_key="", next_retry_at="")
            session.next_check_at = None
            self.log.warning(
                "resume_gave_up",
                provider="codex",
                session=session.ref.key(),
                process=session.describe_process(),
                episode=episode.key,
                attempt=f"{episode.attempts}/{budget}",
            )
            return
        delay = self.config.retry_schedule[episode.attempts]
        due = now + timedelta(seconds=delay)
        self.store.update_episode(episode.key, pending_key="", next_retry_at=due.isoformat())
        session.next_check_at = due
        self.log.info(
            "resume_retry_scheduled",
            provider="codex",
            session=session.ref.key(),
            process=session.describe_process(),
            episode=episode.key,
            attempt=f"{episode.attempts + 1}/{budget}",
            due_at=due,
            delay=delay,
        )

    # -- rediscovery -------------------------------------------------------

    def prune_and_rebind(self) -> None:
        """Drop selections whose session or process no longer exists.

        Called on every rescan. Konsole restarts, tabs close and agents get
        restarted; a selection that no longer refers to a live identity must
        disappear rather than linger and be matched against something new.
        """
        try:
            live = {session.ref.key() for session in self.terminal.list_sessions()}
        except TerminalError:
            self.log.warning("rediscovery_failed", adapter=self.terminal.name)
            return
        for key, session in list(self.sessions.items()):
            if key not in live:
                self.log.info(
                    "session_disappeared",
                    provider=session.provider_name,
                    session=key,
                )
                del self.sessions[key]

    def mark_unsafe(self, key: str, reason: str) -> None:
        session = self.sessions.get(key)
        if session is None:
            return
        session.unsafe_reason = reason
        session.state = SessionState.UNSAFE
        self.log.warning(
            "session_marked_unsafe",
            provider=session.provider_name,
            session=key,
            reason=reason,
        )


def observe_only(config: Config) -> bool:
    return config.mode is Mode.OBSERVE
