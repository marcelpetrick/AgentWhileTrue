"""Provider identity is display-only and fails closed on malformed data."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from agent_watch import identity


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
