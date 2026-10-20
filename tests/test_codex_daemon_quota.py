# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Privacy-redacted app-server response and process/account binding tests."""

import copy
import hashlib
from datetime import UTC, datetime

import pytest

from agent_while_true import codex_daemon_quota as daemon
from agent_while_true.quota import Availability

# Shape observed from the read-only Codex account rate-limit endpoint. No real
# account identifier or quota values are retained in the fixture.
BUCKET = {
    "limitId": "codex",
    "limitName": None,
    "normalModelSlug": None,
    "primary": {"usedPercent": 12, "windowDurationMins": 300, "resetsAt": 1800000000},
    "secondary": {"usedPercent": 23, "windowDurationMins": 10080, "resetsAt": 1800100000},
    "credits": {"hasCredits": False, "unlimited": False, "balance": "0"},
    "individualLimit": None,
    "spendControlReached": False,
    "planType": "plus",
    "rateLimitReachedType": None,
}
RESPONSE = {
    "accountId": "fixture-account",
    "ordinaryUsageAllowed": True,
    "rateLimits": BUCKET,
    "rateLimitsByLimitId": {"codex": BUCKET},
}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    process = tmp_path / "proc" / "77"
    process.mkdir(parents=True)
    home = tmp_path / "profile"
    (process / "environ").write_bytes(f"CODEX_HOME={home}\0".encode())
    monkeypatch.setattr(daemon, "PROC", process.parent)
    monkeypatch.setattr(daemon, "read_start_time", lambda pid: 123)
    key = hashlib.sha256(b"codex-account\0fixture-account").hexdigest()
    monkeypatch.setattr(daemon, "codex_account_key", lambda **kwargs: key)
    payload = copy.deepcopy(RESPONSE)
    calls = []

    def read(selected_home):
        calls.append(selected_home)
        return payload

    monkeypatch.setattr(daemon, "read_daemon_quota", read)
    return daemon.CodexDaemonSource(), payload, process, home, calls


def test_observed_response_is_bound_and_cached(setup):
    source, _, _, home, calls = setup
    first = source.snapshot(pid=77)
    assert first.availability is Availability.AVAILABLE
    assert {window.scope for window in first.windows} == {"session", "weekly"}
    assert first.observed_at is not None
    assert source.snapshot(pid=77) == first
    assert calls == [home]


@pytest.mark.parametrize("allowed", [None, 0, 1, "true", [], {}])
def test_missing_ordinary_permission_is_unknown(setup, allowed):
    source, payload, *_ = setup
    payload["ordinaryUsageAllowed"] = allowed
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ordinaryUsageAllowed", False),
        ("rateLimits", {**BUCKET, "spendControlReached": True}),
        ("rateLimits", {**BUCKET, "rateLimitReachedType": "weekly"}),
    ],
)
def test_provider_denial_is_exhausted(setup, field, value):
    source, payload, *_ = setup
    payload[field] = value
    assert source.snapshot(pid=77).availability is Availability.EXHAUSTED


def test_other_limit_is_never_ignored(setup):
    source, payload, *_ = setup
    other = copy.deepcopy(BUCKET)
    other["primary"]["usedPercent"] = 100
    payload["rateLimitsByLimitId"]["other-model"] = other
    assert source.snapshot(pid=77).availability is Availability.EXHAUSTED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accountId", "different-account"),
        ("accountId", None),
        ("rateLimits", None),
        ("rateLimitsByLimitId", []),
        ("rateLimitsByLimitId", {"unknown": None}),
    ],
)
def test_unbound_or_malformed_response_is_unknown(setup, field, value):
    source, payload, *_ = setup
    payload[field] = value
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("usedPercent", True),
        ("usedPercent", -1),
        ("usedPercent", float("nan")),
        ("usedPercent", None),
        ("windowDurationMins", 0),
        ("windowDurationMins", True),
        ("resetsAt", 10**100),
        ("resetsAt", True),
        ("resetsAt", None),
        ("unknownFutureField", True),
    ],
)
def test_malformed_window_never_available(setup, field, value):
    source, payload, *_ = setup
    payload["rateLimits"]["primary"][field] = value
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


@pytest.mark.parametrize(
    "raw",
    [
        b"CODEX_HOME=relative\0",
        b"CODEX_HOME=\0",
        b"CODEX_HOME=\xff\0",
        b"x" * 65537,
        b"CODEX_HOME=/one\0CODEX_HOME=/two\0",
    ],
)
def test_untrusted_environment_never_queries(setup, raw):
    source, _, process, _, calls = setup
    (process / "environ").write_bytes(raw)
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN
    assert not calls


def test_unreadable_environment_not_defaulted(setup):
    source, _, process, _, calls = setup
    (process / "environ").unlink()
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN
    assert not calls


def test_default_home_requires_successful_environment_read(setup, monkeypatch):
    source, _, process, home, calls = setup
    (process / "environ").write_bytes(b"OTHER=value\0")
    monkeypatch.setattr(daemon.Path, "home", lambda: home)
    assert source.snapshot(pid=77).availability is Availability.AVAILABLE
    assert calls == [home / ".codex"]


@pytest.mark.parametrize("changed", ["pid", "account", "home"])
def test_mid_query_identity_change_rejected(setup, monkeypatch, changed):
    source, payload, process, home, _ = setup

    def read(selected_home):
        if changed == "pid":
            monkeypatch.setattr(daemon, "read_start_time", lambda pid: 456)
        elif changed == "account":
            monkeypatch.setattr(daemon, "codex_account_key", lambda **kwargs: "changed")
        else:
            (process / "environ").write_bytes(f"CODEX_HOME={home}/other\0".encode())
        return payload

    monkeypatch.setattr(daemon, "read_daemon_quota", read)
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


def test_failed_read_cached_briefly_without_inflating_observed_time(setup, monkeypatch):
    source, _, _, _, _ = setup
    clock = [0.0]
    calls = []
    monkeypatch.setattr(daemon.time, "monotonic", lambda: clock[0])

    def broken(home):
        calls.append(home)
        raise OSError("secret must not appear")

    monkeypatch.setattr(daemon, "read_daemon_quota", broken)
    result = source.snapshot(pid=77)
    assert "secret" not in result.note
    assert result.availability is Availability.UNKNOWN
    clock[0] = 9
    assert source.snapshot(pid=77) == result
    assert len(calls) == 1
    clock[0] = 11
    source.snapshot(pid=77)
    assert len(calls) == 2


def test_cache_success_ttl_and_capacity(setup, monkeypatch):
    source, _, _, _, calls = setup
    clock = [0.0]
    monkeypatch.setattr(daemon.time, "monotonic", lambda: clock[0])
    first = source.snapshot(pid=77)
    clock[0] = 61
    source.snapshot(pid=77)
    assert len(calls) == 2
    assert first.observed_at <= datetime.now(UTC)
    for start in range(70):
        monkeypatch.setattr(daemon, "read_start_time", lambda pid, value=start: value)
        source.snapshot(pid=77)
    assert len(source._cache) == 64


def test_missing_pid_or_account_fail_closed(setup, monkeypatch):
    source, *_ = setup
    assert source.snapshot().availability is Availability.UNKNOWN
    monkeypatch.setattr(daemon, "codex_account_key", lambda **kwargs: None)
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


def test_process_gone_isolated(setup, monkeypatch):
    source, *_ = setup

    def gone(pid):
        raise daemon.ProcessGoneError("gone")

    monkeypatch.setattr(daemon, "read_start_time", gone)
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("futureBucket", True),
        ("individualLimit", {}),
        ("primary", None),
        ("spendControlReached", 1),
        ("rateLimitReachedType", False),
        ("rateLimitReachedType", ""),
    ],
)
def test_bucket_ambiguity_fails_closed(setup, field, value):
    source, payload, *_ = setup
    payload["rateLimits"][field] = value
    if field == "primary":
        payload["rateLimits"]["secondary"] = None
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


@pytest.mark.parametrize(
    "mapping", [{"": BUCKET}, {1: BUCKET}, {str(i): BUCKET for i in range(65)}]
)
def test_invalid_bucket_map_key_or_size(setup, mapping):
    source, payload, *_ = setup
    payload["rateLimitsByLimitId"] = mapping
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


def test_nullable_bucket_map_and_primary_supported(setup):
    source, payload, *_ = setup
    payload["rateLimitsByLimitId"] = None
    payload["rateLimits"]["primary"] = None
    assert source.snapshot(pid=77).availability is Availability.AVAILABLE


def test_cache_hit_revalidates_identity_after_lookup(setup, monkeypatch):
    source, *_ = setup
    assert source.snapshot(pid=77).availability is Availability.AVAILABLE
    starts = iter([123, 456])
    monkeypatch.setattr(daemon, "read_start_time", lambda pid: next(starts))
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN


def test_account_or_profile_change_does_not_reuse_cache(setup, monkeypatch):
    source, _, _, _, calls = setup
    assert source.snapshot(pid=77).availability is Availability.AVAILABLE
    monkeypatch.setattr(daemon, "codex_account_key", lambda **kwargs: "new-key")
    assert source.snapshot(pid=77).availability is Availability.UNKNOWN
    assert len(calls) == 2
