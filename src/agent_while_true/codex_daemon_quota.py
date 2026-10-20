# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Account-bound read-only quota for Codex's detached app-server architecture.

No shared rollout is guessed: the selected process supplies a trusted profile,
the private login supplies an opaque account key, and both are revalidated.
"""

import hashlib
import math
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

from agent_while_true.codex_rpc import read_daemon_quota
from agent_while_true.identity import codex_account_key
from agent_while_true.proc import PROC, ProcessGoneError, read_start_time
from agent_while_true.quota import Availability, QuotaSnapshot, QuotaSource, QuotaWindow, unknown

_ENV_LIMIT = 65536
_BUCKET_KEYS = {
    "limitId",
    "limitName",
    "normalModelSlug",
    "primary",
    "secondary",
    "credits",
    "individualLimit",
    "spendControlReached",
    "planType",
    "rateLimitReachedType",
}


def _home(pid: int) -> Path:
    with (PROC / str(pid) / "environ").open("rb") as stream:
        raw = stream.read(_ENV_LIMIT + 1)
    if len(raw) > _ENV_LIMIT:
        raise ValueError("oversized process environment")
    values = [entry[11:] for entry in raw.split(b"\0") if entry.startswith(b"CODEX_HOME=")]
    if not values:
        return Path.home() / ".codex"
    if len(values) != 1:
        raise ValueError("ambiguous process home")
    value = values[0].decode("utf-8", errors="strict")
    home = Path(value)
    if not value or not home.is_absolute():
        raise ValueError("invalid process home")
    return home


def _bound_identity(pid: int) -> tuple[int, Path, str]:
    start = read_start_time(pid)
    home = _home(pid)
    account = codex_account_key(auth_file=home / "auth.json")
    if not account:
        raise ValueError("unavailable account identity")
    return start, home, account


def _window(value: object, scope: str) -> QuotaWindow:
    if not isinstance(value, dict) or set(value) != {
        "usedPercent",
        "windowDurationMins",
        "resetsAt",
    }:
        raise ValueError("invalid quota window")
    used = value["usedPercent"]
    minutes = value["windowDurationMins"]
    reset = value["resetsAt"]
    if type(used) not in {int, float} or not math.isfinite(used) or used < 0:
        raise ValueError("invalid percentage")
    if type(minutes) is not int or minutes <= 0:
        raise ValueError("invalid duration")
    if type(reset) is not int or reset <= 0:
        raise ValueError("invalid reset")
    timestamp = datetime.fromtimestamp(reset, UTC)
    return QuotaWindow("weekly" if minutes >= 10080 else scope, float(used), timestamp)


def _bucket(value: object) -> tuple[list[QuotaWindow], bool]:
    if not isinstance(value, dict) or not set(value) <= _BUCKET_KEYS:
        raise ValueError("invalid quota bucket")
    windows = []
    for name, scope in (("primary", "session"), ("secondary", "weekly")):
        entry = value.get(name)
        if entry is not None:
            windows.append(_window(entry, scope))
    if not windows or value.get("individualLimit") is not None:
        raise ValueError("unsupported quota window")
    spend = value.get("spendControlReached")
    if spend is not None and type(spend) is not bool:
        raise ValueError("invalid spend control")
    reached = value.get("rateLimitReachedType")
    if reached is not None and (not isinstance(reached, str) or not reached):
        raise ValueError("invalid reached type")
    return windows, spend is True or reached is not None


def _snapshot(document: dict[str, object], account: str, observed: datetime) -> QuotaSnapshot:
    identifier = document.get("accountId")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("missing response account")
    received = hashlib.sha256(f"codex-account\0{identifier}".encode()).hexdigest()
    if received != account:
        raise ValueError("response account mismatch")
    ordinary = document.get("ordinaryUsageAllowed")
    if type(ordinary) is not bool:
        raise ValueError("unknown ordinary usage permission")
    windows, blocked = _bucket(document.get("rateLimits"))
    buckets = document.get("rateLimitsByLimitId")
    if buckets is not None:
        if not isinstance(buckets, dict) or len(buckets) > 64:
            raise ValueError("invalid quota bucket map")
        for name, bucket in buckets.items():
            if not isinstance(name, str) or not name:
                raise ValueError("invalid quota bucket identifier")
            extra, denied = _bucket(bucket)
            windows.extend(extra)
            blocked |= denied
    availability = (
        Availability.EXHAUSTED
        if not ordinary or blocked or any(window.exhausted for window in windows)
        else Availability.AVAILABLE
    )
    return QuotaSnapshot(
        "codex",
        availability,
        "codex-app-server",
        observed,
        tuple(dict.fromkeys(windows)),
    )


class CodexDaemonSource(QuotaSource):
    """Bounded account reads cached by live process, profile and account identity."""

    provider = "codex"
    name = "codex-app-server"

    def __init__(self) -> None:
        self._cache: OrderedDict[tuple[int, int, Path, str], tuple[float, QuotaSnapshot]] = (
            OrderedDict()
        )

    def snapshot(self, *, pid: int | None = None) -> QuotaSnapshot:
        if pid is None:
            return unknown(self.provider, self.name, "process identity required")
        try:
            identity = _bound_identity(pid)
            start, home, account = identity
            key = (pid, start, home, account)
            cached = self._cache.get(key)
            now = time.monotonic()
            if cached is not None and now < cached[0]:
                if _bound_identity(pid) != identity:
                    raise ValueError("process identity changed")
                self._cache.move_to_end(key)
                return cached[1]
            try:
                document = read_daemon_quota(home)
                result = _snapshot(document, account, datetime.now(UTC))
            except Exception as exc:  # Failure isolation: an RPC cannot stop other providers.
                result = unknown(
                    self.provider, self.name, f"quota read failed: {type(exc).__name__}"
                )
            if _bound_identity(pid) != identity:
                raise ValueError("process identity changed")
            ttl = 10 if result.availability is Availability.UNKNOWN else 60
            self._cache[key] = (time.monotonic() + ttl, result)
            self._cache.move_to_end(key)
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
            return result
        except (OSError, ValueError, OverflowError, ProcessGoneError) as exc:
            return unknown(self.provider, self.name, f"quota binding failed: {type(exc).__name__}")
