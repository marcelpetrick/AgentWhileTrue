# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

from agent_while_true.event_display import describe_event, explain_reason, read_activity_history


def test_human_messages_keep_outcome_distinctions() -> None:
    assert "checking" in describe_event("event=resume_sent attempt=2")
    assert "Budget recovery verified" in describe_event("event=resume_verified result=resumed")
    assert "not a work restart" in describe_event(
        "event=resume_verified result=armed-provider-wait"
    )
    assert "not a second permission" in describe_event("event=approval_sent reason=resent")
    assert "Continuation outcome verified" in describe_event("event=resume_verified")
    assert "waiting for a fresh sample" in explain_reason("quota-stale")
    assert explain_reason("future-reason") == "future-reason"
    assert "Budget exhausted" in describe_event("event=state_change new=LIMIT_BLOCKED")
    assert "Quota evidence is too old" in describe_event("event=resume_refused reason=quota-stale")
    assert "auto-yes ON" in describe_event("event=auto_yes_toggled enabled=true")
    assert "auto-yes OFF" in describe_event("event=auto_yes_toggled enabled=false")
    assert "toggled" in describe_event("event=auto_yes_toggled")


def test_event_view_does_not_echo_arbitrary_payloads_or_controls() -> None:
    text = describe_event(
        "2026-10-21 01:02:03,000 INFO event=approval_sent provider=claude "
        'attempt=1 secret=private@example.com reason="secret command"'
    )
    assert "01:02:03" in text
    assert "Permission answered once" in text
    assert "provider=claude" in text
    assert "attempt=1" in text
    assert "secret" not in text
    assert "@" not in text
    assert "Diagnostic event" in describe_event("arbitrary raw private text")
    assert "event=unknown" in describe_event('event="\x1b[31mprivate"')
    assert "malformed" in describe_event('event="unterminated')
    assert "oversized" in describe_event("x" * 16385)


def test_readable_events_identify_tab_without_project_or_account_data() -> None:
    text = describe_event(
        "event=approval_sent provider=claude "
        "session=konsole/org.kde.konsole-99/Sessions/2 process=101:456 "
        "title=private-project account=private@example.com"
    )
    assert "session=konsole/org.kde.konsole-99/Sessions/2" in text
    assert "process=101:456" in text
    assert "private" not in text
    assert "session=" not in describe_event("event=approval_sent session=private@example.com")
    assert "process=" not in describe_event("event=approval_sent process=private-project")


def test_activity_tail_keeps_sampling_noise_out_without_rewriting_logs(tmp_path) -> None:
    path = tmp_path / "events.log"
    content = (
        "event=approval_sent provider=claude\n" + "event=supervision_interval seconds=60\n" * 120
    )
    path.write_text(content)
    assert read_activity_history(path, limit=2) == ["event=approval_sent provider=claude"]
    assert read_activity_history(path, limit=0) == []
    assert path.read_text() == content
