# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provider identity is display-only and fails closed on malformed data."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from agent_while_true import identity


def _jwt(payload: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def test_codex_email_reads_only_an_owner_private_id_claim(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"id_token": _jwt({"email": "me@example.com"})}}))
    auth.chmod(0o600)
    assert identity.codex_email(auth_file=auth) == "me@example.com"


def test_codex_email_refuses_public_or_malformed_auth_files(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"id_token": "secret-not-a-jwt"}}))
    auth.chmod(0o644)
    assert identity.codex_email(auth_file=auth) is None
    auth.chmod(0o600)
    assert identity.codex_email(auth_file=auth) is None


def test_codex_account_key_is_opaque_and_requires_private_auth(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"account_id": "account-secret"}}))
    auth.chmod(0o600)

    key = identity.codex_account_key(auth_file=auth)

    assert key is not None
    assert "account-secret" not in key
    auth.chmod(0o644)
    assert identity.codex_account_key(auth_file=auth) is None


def test_claude_email_uses_the_provider_auth_status(monkeypatch) -> None:
    monkeypatch.setattr(identity.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        identity.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, json.dumps({"loggedIn": True, "email": "claude@example.com"}), ""
        ),
    )
    assert identity.claude_email() == "claude@example.com"


def test_claude_email_refuses_invalid_or_logged_out_status(monkeypatch) -> None:
    monkeypatch.setattr(identity.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        identity.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, json.dumps({"loggedIn": False, "email": "wrong@example.com"}), ""
        ),
    )
    assert identity.claude_email() is None


def test_provider_accounts_marks_unknown_identity(monkeypatch) -> None:
    monkeypatch.setattr(identity, "codex_email", lambda: None)
    monkeypatch.setattr(identity, "claude_email", lambda: "claude@example.com")
    assert identity.provider_accounts() == {
        "codex": "unavailable",
        "claude": "claude@example.com",
    }


def test_codex_session_account_distinguishes_profile_home(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / ".codex-dmo"
    profile.mkdir()
    auth = profile / "auth.json"
    auth.write_text(json.dumps({"tokens": {"id_token": _jwt({"email": "work@example.com"})}}))
    auth.chmod(0o600)
    monkeypatch.setattr(identity, "_process_environment_value", lambda pid, key: str(profile))

    account = identity.codex_session_account(123)

    assert account.profile == "codex-dmo"
    assert account.email == "work@example.com"
    assert account.label() == "codex-dmo · work@example.com"


def _claude_cli(monkeypatch, emails: dict[str, str]) -> list[str]:
    """Fake ``claude auth status --json``, answering per CLAUDE_CONFIG_DIR."""
    calls: list[str] = []

    def run(command, **kwargs):
        config_dir = kwargs["env"]["CLAUDE_CONFIG_DIR"]
        calls.append(config_dir)
        email = emails.get(config_dir)
        payload = json.dumps({"loggedIn": email is not None, "email": email or ""})
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(identity.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(identity.subprocess, "run", run)
    return calls


def test_claude_session_account_distinguishes_profile_home(tmp_path: Path, monkeypatch) -> None:
    """Two Claude sessions on one machine can hold two different logins.

    Observed live: with ``~/.claude`` and ``~/.claude-dmo`` both present, every
    session was labelled with the supervisor's own account.
    """
    personal = tmp_path / ".claude"
    work = tmp_path / ".claude-dmo"
    _claude_cli(
        monkeypatch,
        {str(personal): "me@example.com", str(work): "me@work.example.com"},
    )
    homes = {11: str(personal), 22: str(work)}
    monkeypatch.setattr(identity, "_process_environment_value", lambda pid, key: homes[pid])

    assert identity.session_account("claude", 11).label() == "claude · me@example.com"
    assert identity.session_account("claude", 22).label() == "claude-dmo · me@work.example.com"


def test_claude_session_account_falls_back_to_the_default_home(tmp_path: Path, monkeypatch) -> None:
    default = tmp_path / ".claude"
    _claude_cli(monkeypatch, {str(default): "me@example.com"})
    monkeypatch.setattr(identity.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(identity, "_process_environment_value", lambda pid, key: None)

    assert identity.session_account("claude", 7).label() == "claude · me@example.com"


def test_claude_session_account_is_resolved_once_per_profile(tmp_path: Path, monkeypatch) -> None:
    """The CLI is spawned per profile, not per selected session."""
    home = tmp_path / ".claude"
    calls = _claude_cli(monkeypatch, {str(home): "me@example.com"})
    monkeypatch.setattr(identity, "_process_environment_value", lambda pid, key: str(home))

    labels = {identity.session_account("claude", pid).label() for pid in (1, 2, 3, 4)}

    assert labels == {"claude · me@example.com"}
    assert calls == [str(home)]


def test_an_unidentifiable_claude_profile_reports_unavailable(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "somewhere-else"
    _claude_cli(monkeypatch, {})
    monkeypatch.setattr(identity, "_process_environment_value", lambda pid, key: str(home))

    account = identity.session_account("claude", 5)

    assert account.profile == "claude-profile"
    assert account.email == "unavailable"
    assert account.label() == "claude-profile"


def test_a_failed_claude_lookup_is_retried_rather_than_cached(tmp_path, monkeypatch) -> None:
    """`claude auth status` reaches the network, so a timeout must not be final.

    Caching the failure would pin the profile to "unavailable" for the whole run,
    where before the per-profile cache every session and rediscovery retried.
    """
    home = tmp_path / ".claude"
    answers = [None, "me@example.com"]
    calls: list[str] = []

    def claude_email(*, config_dir=None):
        calls.append(str(config_dir))
        return answers.pop(0)

    monkeypatch.setattr(identity, "claude_email", claude_email)
    monkeypatch.setattr(identity, "_process_environment_value", lambda pid, key: str(home))

    assert identity.session_account("claude", 1).email == "unavailable"
    assert identity.session_account("claude", 2).email == "me@example.com"
    # The resolved answer is cached; only the failure was retried.
    assert identity.session_account("claude", 3).email == "me@example.com"
    assert calls == [str(home), str(home)]
