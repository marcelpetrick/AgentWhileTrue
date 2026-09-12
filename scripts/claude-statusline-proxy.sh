#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

#
# Claude Code status-line proxy.
#
# Claude Code pipes a JSON document to its configured status-line command on
# every render. That document carries the usage numbers agent-watch wants:
# five-hour and seven-day utilisation and their reset timestamps. This script
# captures those into a process-bound, per-session file that agent-watch reads
# passively, then hands the untouched JSON to whatever status-line command the
# user already had, so an existing status line keeps working exactly as before.
#
# Install:
#   1. Note your current statusLine command from ~/.claude/settings.json.
#   2. Point statusLine at this script.
#   3. Set AGENT_WATCH_STATUSLINE_CHAIN to your original command.
#
# Example ~/.claude/settings.json fragment:
#
#   "statusLine": {
#     "type": "command",
#     "command": "AGENT_WATCH_CLAUDE_PID=$PPID \
#                 AGENT_WATCH_STATUSLINE_CHAIN=~/.claude/my-statusline.sh \
#                 ~/.local/share/agent-watch/claude-statusline-proxy.sh"
#   }
#
# The proxy must never be the reason a status line stops rendering, so every
# failure here is swallowed and the original command still runs.

set -uo pipefail
umask 077

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/agent-watch"
CHAIN="${AGENT_WATCH_STATUSLINE_CHAIN:-}"
CLAUDE_PID="${AGENT_WATCH_CLAUDE_PID:-}"

payload="$(cat)"

capture() {
    local quota_dir="$STATE_DIR/quota"
    mkdir -p -- "$quota_dir" 2> /dev/null || return 0
    chmod 700 -- "$STATE_DIR" 2> /dev/null || true
    chmod 700 -- "$quota_dir" 2> /dev/null || true
    command -v python3 > /dev/null 2>&1 || return 0

    QUOTA_DIR="$quota_dir" CLAUDE_PID="$CLAUDE_PID" python3 -c '
import hashlib, json, os, sys, tempfile, time
from pathlib import Path

def process_facts(pid):
    try:
        proc = Path("/proc") / str(pid)
        comm = (proc / "comm").read_text(errors="replace").strip()
        cmdline = tuple(part for part in (proc / "cmdline").read_bytes().split(b"\0") if part)
        raw = (proc / "stat").read_text(errors="replace")
        close = raw.rfind(")")
        fields = raw[close + 2:].split() if close >= 0 else []
        if len(fields) <= 19:
            return None
        is_claude = comm == "claude"
        if cmdline:
            executable = os.path.basename(os.fsdecode(cmdline[0]))
            decoded = tuple(os.fsdecode(part) for part in cmdline)
            is_claude = is_claude or executable == "claude" or any(
                "@anthropic-ai/claude-code" in part for part in decoded
            )
        if not is_claude:
            return None
        return {"pid": pid, "start_time": int(fields[19])}
    except (OSError, ValueError):
        return None

def parent_pid(pid):
    try:
        for line in (Path("/proc") / str(pid) / "status").read_text().splitlines():
            if line.startswith("PPid:"):
                return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0

candidate = int(os.environ.get("CLAUDE_PID", "0")) if os.environ.get("CLAUDE_PID", "").isdigit() else 0
process = process_facts(candidate) if candidate > 1 else None
ancestor = os.getppid()
for _ in range(16):
    if process is not None or ancestor <= 1:
        break
    process = process_facts(ancestor)
    ancestor = parent_pid(ancestor)

try:
    document = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
if not isinstance(document, dict) or process is None:
    raise SystemExit(0)
session_id = document.get("session_id")
if not isinstance(session_id, str) or not session_id or len(session_id) > 512:
    raise SystemExit(0)
session_key = hashlib.sha256(session_id.encode()).hexdigest()
source = document.get("rate_limits") or document.get("usage") or {}
if not isinstance(source, dict):
    source = {}
captured = {
    "source": "claude",
    "updated_at": int(time.time()),
    "session_key": session_key,
    "process": process,
}
for key in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
    value = source.get(key)
    if isinstance(value, dict):
        captured[key] = value
quota_dir = Path(os.environ["QUOTA_DIR"])
output = quota_dir / f"claude-{session_key}.json"
descriptor, temporary_name = tempfile.mkstemp(prefix=f"{output.name}.tmp.", dir=quota_dir)
temporary = Path(temporary_name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(captured, handle, separators=(",", ":"))
    temporary.chmod(0o600)
    temporary.replace(output)
except Exception:
    temporary.unlink(missing_ok=True)
' <<< "$payload" > /dev/null 2>&1 || true
}

capture

if [ -n "$CHAIN" ]; then
    # Hand the original document, unmodified, to the user's own status line.
    printf '%s' "$payload" | eval "$CHAIN"
fi
