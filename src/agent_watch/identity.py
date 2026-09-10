# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Display-only provider account identity discovery.

Account emails are sensitive presentation data. They are read once when an
interactive dashboard starts, kept only in memory, and never passed to the
event logger or state store. Failure to identify an account is rendered as
unavailable; identity is never inferred from quota or process state.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_MAX_AUTH_BYTES = 1024 * 1024
_AUTH_TIMEOUT_SECONDS = 5.0
_PROFILE = re.compile(r"[A-Za-z0-9._-]{1,64}")


@dataclass(frozen=True, slots=True)
class SessionAccount:
    """Display-only account identity for one live provider process."""

    profile: str
    email: str

    def label(self) -> str:
        if self.email == "unavailable":
            return self.profile
        return f"{self.profile} · {self.email}"


def _valid_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        return None
    return email


def _decode_jwt_payload(token: object) -> dict[str, object] | None:
    if not isinstance(token, str) or token.count(".") != 2:
        return None
    try:
        encoded = token.split(".", 2)[1]
        encoded += "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded))
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _codex_auth(auth_file: Path | None = None) -> dict[str, object] | None:
    """Read an owner-private Codex auth document without exposing its values."""
    path = auth_file or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
    try:
        stat = path.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077 or stat.st_size > _MAX_AUTH_BYTES:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    return document


def codex_email(*, auth_file: Path | None = None) -> str | None:
    """Read only the email claim from Codex's owner-private OAuth ID token."""
    document = _codex_auth(auth_file)
    if document is None:
        return None
    tokens = document.get("tokens")
    if not isinstance(tokens, dict):
        return None
    payload = _decode_jwt_payload(tokens.get("id_token"))
    return _valid_email(payload.get("email")) if payload else None


def codex_account_key(*, auth_file: Path) -> str | None:
    """Return a memory-only opaque key for a positively identified account."""
    document = _codex_auth(auth_file)
    if document is None:
        return None
    tokens = document.get("tokens")
    if not isinstance(tokens, dict):
        return None
    account_id = tokens.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        return None
    return hashlib.sha256(f"codex-account\0{account_id}".encode()).hexdigest()


def _process_environment_value(pid: int, key: str) -> str | None:
    """Read one named value for display discovery without retaining the rest."""
    try:
        raw = (Path("/proc") / str(pid) / "environ").read_bytes()
    except OSError:
        return None
    prefix = f"{key}=".encode()
    for entry in raw.split(b"\0"):
        if entry.startswith(prefix):
            return entry[len(prefix) :].decode(errors="replace")
    return None


def codex_session_account(pid: int) -> SessionAccount:
    """Resolve the Codex home, profile label, and email for one process.

    Zsh expands functions and aliases before spawning Codex, so their names are
    unavailable afterward. A profile-selecting ``CODEX_HOME`` does survive and
    is the reliable distinction between the default and ``codex-dmo`` logins.
    """
    configured = _process_environment_value(pid, "CODEX_HOME")
    home = Path(configured).expanduser() if configured else Path.home() / ".codex"
    name = home.name
    if name == ".codex":
        profile = "codex"
    elif name.startswith(".codex-") and _PROFILE.fullmatch(name):
        profile = f"codex-{name.removeprefix('.codex-')}"
    else:
        profile = "codex-profile"
    return SessionAccount(profile, codex_email(auth_file=home / "auth.json") or "unavailable")


def session_account(provider: str, pid: int) -> SessionAccount:
    """Return a per-process display identity without logging or persistence."""
    if provider == "codex":
        return codex_session_account(pid)
    if provider == "claude":
        return SessionAccount("claude", claude_email() or "unavailable")
    return SessionAccount(provider, "unavailable")


def claude_email() -> str | None:
    """Ask Claude Code for its authenticated email through its public CLI."""
    executable = shutil.which("claude")
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [executable, "auth", "status", "--json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_AUTH_TIMEOUT_SECONDS,
            check=False,
        )
        document = json.loads(completed.stdout) if completed.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    if not isinstance(document, dict) or document.get("loggedIn") is not True:
        return None
    return _valid_email(document.get("email"))


def provider_accounts() -> dict[str, str]:
    """Return display values for both supported providers, without caching."""
    return {
        "codex": codex_email() or "unavailable",
        "claude": claude_email() or "unavailable",
    }
