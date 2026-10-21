# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later

"""Same-model capacity retries are bounded, quota-gated and process-bound."""

from dataclasses import replace
from datetime import timedelta

import pytest

from agent_while_true import state_store
from agent_while_true.config import Config, Mode, Policy, load
from agent_while_true.policy import capacity_idempotency_key, evaluate
from agent_while_true.quota import Availability, QuotaWindow
from agent_while_true.states import ActionState, SessionState
from tests import harness, screens

COMPOSER = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK} Ask Codex to do anything"
WORKING = ["• Working (1s · esc to interrupt)", "", COMPOSER]


def setup_capacity(tmp_path, monkeypatch, *, mode=Mode.AUTO, availability=Availability.AVAILABLE):
    kit = harness.build(tmp_path, config=Config(mode=mode))
    info = kit.inspector.add_codex(4321)
    ref = kit.terminal.add(
        "/Sessions/1", shell_pid=100, foreground_pid=info.pid, screen=screens.CODEX_MODEL_CAPACITY
    )
    kit.supervisor.select(ref, info.identity, "codex", "synthetic capacity")
    kit.quota["codex"].availability = availability
    monkeypatch.setattr(state_store, "_now_text", lambda: kit.clock.now().isoformat())
    return kit, kit.supervisor.sessions[ref.key()]


def advance(kit, seconds):
    kit.clock.advance(seconds)
    harness.refresh_quota(kit)
    return kit.supervisor.tick()[0]


def test_capacity_waits_then_submits_only_continue_and_confirms_sustained_work(
    tmp_path, monkeypatch
):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    first = kit.supervisor.tick()[0]
    assert first.reason == "capacity-retry-not-due"
    assert first.retry_at == kit.clock.now() + timedelta(seconds=5)
    assert session.state is SessionState.CAPACITY_BLOCKED
    assert not kit.supervisor.store.episodes
    assert not kit.sent
    assert advance(kit, 5).allowed
    assert kit.sent == [("/Sessions/1", "\x1b[200~continue\x1b[201~\r")]
    assert kit.supervisor.activity.capacity_recoveries == 0
    kit.terminal.set_screen("/Sessions/1", WORKING)
    assert advance(kit, 1).reason == "verifying"
    assert kit.supervisor.activity.capacity_recoveries == 0
    assert advance(kit, 3).reason == "capacity-recovery-verified"
    assert kit.supervisor.activity.capacity_recoveries == 1
    assert kit.supervisor.activity.budget_restarts == 0
    assert not kit.supervisor.store.episodes
    assert kit.supervisor.activity.unblock_actions == 1


@pytest.mark.parametrize("availability", [Availability.UNKNOWN, Availability.EXHAUSTED])
def test_capacity_never_uses_clock_exception_for_missing_or_exhausted_quota(
    tmp_path, monkeypatch, availability
):
    kit, _ = setup_capacity(tmp_path, monkeypatch, availability=availability)
    kit.supervisor.tick()
    assert not advance(kit, 100000).allowed
    assert not kit.sent


@pytest.mark.parametrize("mode", [Mode.OBSERVE, Mode.ASK])
def test_capacity_requires_auto_not_ask_confirmation(tmp_path, monkeypatch, mode):
    kit, _ = setup_capacity(tmp_path, monkeypatch, mode=mode)
    kit.supervisor.confirm = lambda *args: True
    kit.supervisor.tick()
    assert advance(kit, 5).reason == "capacity-requires-full-auto"
    assert not kit.sent
    assert not kit.supervisor.store.records


def test_capacity_stale_quota_and_other_exhausted_windows_veto(tmp_path, monkeypatch):
    kit, _ = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.tick()
    kit.clock.advance(3600)
    assert kit.supervisor.tick()[0].reason == "quota-stale"
    harness.refresh_quota(kit)
    kit.quota["codex"].windows = (QuotaWindow("weekly", 100, kit.clock.now() + timedelta(days=1)),)
    assert not kit.supervisor.tick()[0].allowed
    assert not kit.sent


def test_capacity_opt_out_and_master_switch_apply(tmp_path, monkeypatch):
    kit, _ = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.config = replace(
        kit.supervisor.config, policy=Policy(allow_codex_capacity_retry=False)
    )
    kit.supervisor.tick()
    assert advance(kit, 5).reason == "action-requires-policy:allow_codex_capacity_retry"
    kit.supervisor.config = replace(kit.supervisor.config, policy=Policy(resume_after_reset=False))
    assert not kit.supervisor.tick()[0].allowed
    assert not kit.sent
    assert (
        load(
            environ={"AGENT_WHILE_TRUE_ALLOW_CODEX_CAPACITY_RETRY": "false"}
        ).policy.allow_codex_capacity_retry
        is False
    )


def test_capacity_failure_spends_persistent_budget_despite_redraws_and_restart(
    tmp_path, monkeypatch
):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.tick()
    assert advance(kit, 5).allowed
    assert not advance(kit, 1).allowed
    key = session.pending_key
    record = kit.supervisor.store.records[key]
    assert record.state is ActionState.FAILED
    assert record.attempts == 1
    # A history/elapsed-time redraw cannot mint a new idempotency key.
    kit.terminal.set_screen(
        "/Sessions/1", ["Unrelated prior output", *screens.CODEX_MODEL_CAPACITY]
    )
    assert advance(kit, 29).reason == "capacity-retry-not-due"
    assert advance(kit, 1).allowed
    advance(kit, 1)
    assert kit.supervisor.store.records[key].attempts == 2
    kit.supervisor.store = state_store.StateStore.in_directory(tmp_path).load(now=kit.clock.now())
    session.capacity_first_seen = None
    session.pending_key = ""
    session.attempts_since_success = 0
    assert advance(kit, 59).reason == "capacity-retry-not-due"
    assert advance(kit, 1).allowed
    advance(kit, 1)
    assert advance(kit, 1000).reason == "max-resume-attempts-reached"
    assert len(kit.sent) == 3
    assert kit.supervisor.store.records[key].attempts == 3


def test_capacity_retains_spent_budget_beyond_action_history_ttl(tmp_path, monkeypatch):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.tick()
    advance(kit, 5)
    advance(kit, 1)
    key = session.pending_key
    loaded = state_store.StateStore.in_directory(tmp_path).load(
        now=kit.clock.now() + timedelta(days=2)
    )
    assert loaded.attempts_for(key) == 1


@pytest.mark.parametrize("timestamp", ["invalid", "2026-10-01T00:00:00"])
def test_capacity_corrupt_backoff_fails_closed(tmp_path, monkeypatch, timestamp):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    key = capacity_idempotency_key(session.ref, session.identity)
    record = kit.supervisor.store.plan(
        key, provider="codex", session=session.ref.key(), process=session.describe_process()
    )
    kit.supervisor.store.mark(key, ActionState.FAILED)
    record.updated_at = timestamp
    assert kit.supervisor.tick()[0].reason == "capacity-state-invalid"
    assert not kit.sent


@pytest.mark.parametrize("field", ["provider", "session", "process"])
def test_capacity_persisted_binding_mismatch_fails_closed(tmp_path, monkeypatch, field):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    key = capacity_idempotency_key(session.ref, session.identity)
    record = kit.supervisor.store.plan(
        key, provider="codex", session=session.ref.key(), process=session.describe_process()
    )
    setattr(record, field, "mismatched")
    assert kit.supervisor.tick()[0].reason == "capacity-state-invalid"
    assert not kit.sent


@pytest.mark.parametrize("state", [ActionState.PLANNED, ActionState.SENT])
def test_capacity_restored_intent_is_not_replayed_or_credited(tmp_path, monkeypatch, state):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    key = capacity_idempotency_key(session.ref, session.identity)
    kit.supervisor.store.plan(
        key, provider="codex", session=session.ref.key(), process=session.describe_process()
    )
    if state is ActionState.SENT:
        kit.supervisor.store.mark(key, state)
        kit.terminal.set_screen("/Sessions/1", WORKING)
    kit.supervisor.tick()
    advance(kit, 5)
    assert not kit.sent
    assert kit.supervisor.activity.capacity_recoveries == 0
    if state is ActionState.SENT:
        assert kit.supervisor.store.records[key].state is ActionState.VERIFIED
    else:
        assert kit.supervisor.store.records[key].state is ActionState.PLANNED


@pytest.mark.parametrize("drift", ["pid", "draft", "quota", "veto"])
@pytest.mark.parametrize("read_number", [1, 2])
def test_capacity_revalidates_immediately_before_send(tmp_path, monkeypatch, drift, read_number):
    kit, _ = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.tick()
    reads = [0]

    def change(session_id):
        reads[0] += 1
        if reads[0] != read_number:
            return
        if drift == "pid":
            kit.inspector.add_codex(4321, start_time=999)
        elif drift == "quota":
            kit.quota["codex"].availability = Availability.UNKNOWN
        elif drift == "draft":
            kit.terminal.set_screen(
                session_id,
                [
                    s.replace("Ask Codex to do anything", "my draft")
                    for s in screens.CODEX_MODEL_CAPACITY
                ],
            )
        else:
            kit.terminal.set_screen(
                session_id, [*screens.CODEX_MODEL_DOWNGRADE, *screens.CODEX_MODEL_CAPACITY]
            )

    kit.terminal.after_read = change
    assert not advance(kit, 5).allowed
    assert not kit.sent


def test_capacity_transport_errors_spend_attempts(tmp_path, monkeypatch):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    kit.terminal.send_fails = True
    kit.supervisor.tick()
    assert advance(kit, 5).reason == "send-failed"
    assert kit.supervisor.store.attempts_for(session.pending_key) == 1
    assert advance(kit, 30).reason == "send-failed"
    assert advance(kit, 60).reason == "send-failed"
    assert advance(kit, 60).reason == "max-resume-attempts-reached"
    assert not kit.sent


def test_returning_capacity_after_success_keeps_remaining_lifetime_budget(tmp_path, monkeypatch):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.tick()
    advance(kit, 5)
    key = session.pending_key
    kit.terminal.set_screen("/Sessions/1", WORKING)
    advance(kit, 1)
    assert advance(kit, 3).reason == "capacity-recovery-verified"
    kit.terminal.set_screen("/Sessions/1", screens.CODEX_MODEL_CAPACITY)
    kit.supervisor.store = state_store.StateStore.in_directory(tmp_path).load(now=kit.clock.now())
    assert advance(kit, 29).reason == "capacity-retry-not-due"
    assert advance(kit, 1).allowed
    assert kit.supervisor.store.attempts_for(key) == 2
    assert kit.supervisor.activity.capacity_recoveries == 1


def test_capacity_idle_composer_is_not_verified_progress(tmp_path, monkeypatch):
    kit, _ = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.tick()
    advance(kit, 5)
    kit.terminal.set_screen("/Sessions/1", [COMPOSER])
    assert advance(kit, 1).reason == "verify:still-blocked"
    assert kit.supervisor.activity.capacity_recoveries == 0


def test_capacity_transient_working_does_not_earn_success(tmp_path, monkeypatch):
    kit, _ = setup_capacity(tmp_path, monkeypatch)
    kit.supervisor.tick()
    advance(kit, 5)
    kit.terminal.set_screen("/Sessions/1", WORKING)
    assert advance(kit, 1).reason == "verifying"
    kit.terminal.set_screen("/Sessions/1", screens.CODEX_MODEL_CAPACITY)
    assert advance(kit, 3).reason == "verify:still-blocked"
    assert kit.supervisor.activity.capacity_recoveries == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capacity_prompt", False),
        ("composer_empty", False),
        ("input_ready", False),
        ("retry_prompt", True),
    ],
)
def test_capacity_gate_does_not_trust_unvalidated_flags(tmp_path, monkeypatch, field, value):
    kit, session = setup_capacity(tmp_path, monkeypatch)
    observation = kit.supervisor.observe(session.ref)
    request = kit.supervisor._request(session, observation)
    recognition = replace(request.recognition, **{field: value})
    if field == "retry_prompt":
        request = replace(request, codex_retry=True)
    assert not evaluate(replace(request, recognition=recognition)).allowed
