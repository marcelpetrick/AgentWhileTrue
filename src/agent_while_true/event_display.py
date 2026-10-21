# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Plain-language views of structured metadata, without arbitrary field text."""

import re
import shlex
from pathlib import Path

from agent_while_true.logging_setup import read_history

_MESSAGES = {
    "approval_sent": "Permission answered once",
    "approval_refused": "Permission left for you",
    "approval_status": "Permission automation status updated",
    "resume_sent": "Continuation sent; checking the result",
    "resume_verified": "Continuation outcome verified",
    "resume_not_verified": "Still blocked; continuation not confirmed",
    "resume_verification_failed": "Could not verify recovery; inspect the agent tab",
    "resume_send_failed": "Continuation could not be sent",
    "resume_refused": "Waiting safely; continuation not allowed yet",
    "resume_gave_up": "Retry budget spent; inspect the agent tab",
    "resume_retry_scheduled": "Next bounded continuation attempt scheduled",
    "state_change": "Agent state changed",
    "session_selected": "Agent added to this watch",
    "mode_changed": "Automation mode changed",
    "auto_yes_toggled": "One-time permission approvals toggled",
    "input_yielded": "Input control handed to another watcher",
    "input_rearmed": "Background watcher regained input control",
    "supervision_interval": "Observation time recorded",
    "whip_delivered": "Operator reminder delivered",
    "whip_skipped": "Operator reminder skipped safely",
    "whip_cracked": "Operator reminder requested",
}
_REASONS = {
    "quota-stale": "Quota evidence is too old; waiting for a fresh sample",
    "quota-unknown": "Quota is unknown; availability is not assumed",
    "observe-mode": "Observe mode: no input is sent",
    "auto-yes-off": "Press y in full-auto to allow exact one-time permissions",
    "no-input-control": "Another watcher owns input control",
    "unsupported-permission-layout": "Unrecognized permission layout; answer in its tab",
    "conflicting-permission-context": "Conflicting prompt context; answer in its tab",
    "dashboard-paused": "Paused: no input is sent",
    "retry-budget-exhausted": "All bounded attempts were used; inspect the agent tab",
    "already-approved": "This permission was already answered",
    "unanswered-after-resend": "Permission still visible after both answers; answer in its tab",
    "unanswered-no-resend": "Codex permission still visible; answer in its tab (no resend)",
    "process-gone": "Agent exited; no input can be sent",
    "reset-grace-period": "Waiting for the safety grace period after reset",
    "retry-not-due": "Waiting for the next bounded attempt",
    "reset-not-reached": "The provider's reset time has not arrived",
    "ready-without-preceding-limit": "No limit was witnessed in this watch; inspect the agent tab",
    "verifying": "Checking whether the continuation worked",
    "prompt-changed": "Prompt changed during the final check; nothing sent",
    "all-conditions-met": "All continuation checks passed",
    "resume-sent": "Continuation sent; verification pending",
    "resume-verified": "Budget recovery verified",
    "verify:armed-provider-wait": "Claude will wait itself; work has not restarted yet",
}
_STATES = {
    "ACTIVE": "Working screen observed",
    "LIMIT_WARNING": "Usage is nearly spent",
    "LIMIT_BLOCKED": "Budget exhausted; waiting for renewal",
    "WAITING_FOR_RESET": "Waiting for the provider reset",
    "RESET_GRACE_PERIOD": "Reset reached; allowing the safety grace period",
    "READY_TO_RESUME": "Continuation prompt detected; safety checks still apply",
    "APPROVAL_PENDING": "Tool permission needs an answer",
    "PROCESS_GONE": "Agent exited or was replaced",
    "UNSAFE": "Automatic input blocked by the safety gate",
}
_TOKEN = re.compile(r"^[A-Za-z0-9_./:-]{1,100}$")
_ROUTINE = re.compile(r"(?:^|\s)event=supervision_interval(?:\s|$)")


def read_activity_history(path: Path, *, limit: int = 50) -> list[str]:
    """Keep routine sampling out of the activity feed, within a bounded tail."""
    if limit <= 0:
        return []
    rows = read_history(path, limit=max(200, limit * 10))
    return [row for row in rows if not _ROUTINE.search(row)][-limit:]


def explain_reason(reason: str) -> str:
    """Known reasons get guidance; other metadata IDs remain recognizable."""
    message = _REASONS.get(reason)
    return f"{message} [{reason}]" if message else reason


def describe_event(line: str) -> str:
    """Render only known messages and a small allowlist of metadata tokens."""
    if len(line) > 16384:
        return "Event unavailable (oversized record)"
    try:
        tokens = shlex.split(line)
    except ValueError:
        return "Event unavailable (malformed record)"
    fields = dict(token.split("=", 1) for token in tokens if "=" in token)
    event = fields.get("event", "unknown")
    safe_event = event if _TOKEN.fullmatch(event) else "unknown"
    message = _MESSAGES.get(event, "Diagnostic event")
    if event == "resume_verified" and fields.get("result") == "resumed":
        message = "Budget recovery verified; agent screen shows progress"
    if event == "resume_verified" and fields.get("result") == "armed-provider-wait":
        message = "Claude automatic wait armed; not a work restart"
    if event == "approval_sent" and fields.get("reason") == "resent":
        message = "Permission answer resent once; not a second permission"
    if event == "auto_yes_toggled":
        if fields.get("enabled") == "true":
            message = "Permission auto-yes ON; only effective in full-auto with input control"
        elif fields.get("enabled") == "false":
            message = "Permission auto-yes OFF; requests wait for you"
    if event == "state_change":
        message = _STATES.get(fields.get("new", ""), message)
    if event in {"resume_refused", "approval_refused", "approval_status"}:
        message = _REASONS.get(fields.get("reason", ""), message)
    context = []
    session = fields.get("session", "")
    if re.fullmatch(r"(?:konsole|fake)/[A-Za-z0-9_.-]+/Sessions/[0-9]+", session):
        context.append(f"session={session}")
    process = fields.get("process", "")
    if re.fullmatch(r"[0-9]+:[0-9]+", process):
        context.append(f"process={process}")
    for key in (
        "provider",
        "attempt",
        "state",
        "previous",
        "new",
        "mode",
        "reason",
        "controller_pid",
    ):
        value = fields.get(key, "")
        if _TOKEN.fullmatch(value):
            context.append(f"{key}={value}")
    stamp = (
        tokens[1][:8]
        if len(tokens) > 1 and re.fullmatch(r"\d\d:\d\d:\d\d,\d{3}", tokens[1])
        else ""
    )
    return " ".join(part for part in (stamp, message, f"[event={safe_event}]", *context) if part)
