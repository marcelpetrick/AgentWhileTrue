"""Memory-only provider health from the providers' public status pages."""

from __future__ import annotations

import enum
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

STATUS_URLS = {
    "openai": "https://status.openai.com/api/v2/summary.json",
    "anthropic": "https://status.anthropic.com/api/v2/summary.json",
}
WATCHED_COMPONENTS = {
    "openai": ("Responses", "Login"),
    "anthropic": ("Claude Code", "Claude API (api.anthropic.com)"),
}
REQUEST_TIMEOUT_SECONDS = 3.0


class HealthState(enum.StrEnum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OUTAGE = "OUTAGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider: str
    state: HealthState
    detail: str
    checked_at: datetime | None = None


def unknown_health(provider: str, detail: str = "not-checked") -> ProviderHealth:
    return ProviderHealth(provider, HealthState.UNKNOWN, detail)


def _state(statuses: list[str], indicator: str) -> HealthState:
    values = {value.casefold() for value in statuses}
    if values & {"major_outage", "critical"} or indicator.casefold() == "critical":
        return HealthState.OUTAGE
    if values - {"operational"} or indicator.casefold() not in {"", "none"}:
        return HealthState.DEGRADED
    return HealthState.ONLINE


def parse_summary(provider: str, document: object, *, now: datetime) -> ProviderHealth:
    """Reduce a Statuspage summary to the components relevant to this tool."""
    if not isinstance(document, dict):
        return unknown_health(provider, "malformed-status")
    wanted = WATCHED_COMPONENTS[provider]
    components = document.get("components")
    if not isinstance(components, list):
        return unknown_health(provider, "missing-components")
    selected: list[tuple[str, str]] = []
    for component in components:
        if not isinstance(component, dict) or component.get("name") not in wanted:
            continue
        status = component.get("status")
        if isinstance(status, str):
            selected.append((str(component["name"]), status))
    if len(selected) != len(wanted):
        return unknown_health(provider, "component-not-found")
    overall = document.get("status")
    indicator = overall.get("indicator", "") if isinstance(overall, dict) else ""
    state = _state([status for _, status in selected], str(indicator))
    detail = ", ".join(f"{name}={status}" for name, status in selected)
    return ProviderHealth(provider, state, detail, now)


def fetch_summary(provider: str, *, now: datetime | None = None) -> ProviderHealth:
    """Fetch one provider summary without credentials or model requests."""
    request = urllib.request.Request(
        STATUS_URLS[provider], headers={"User-Agent": "AgentWhileTrue service-health"}
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            document = json.loads(response.read(512 * 1024))
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return unknown_health(provider, "status-unreachable")
    return parse_summary(provider, document, now=now or datetime.now(UTC))


@dataclass(slots=True)
class HealthMonitor:
    """Poll status pages off the supervisor thread and expose the latest cache."""

    interval: float = 60.0
    fetch: Callable[[str], ProviderHealth] = fetch_summary
    _lock: threading.Lock = field(init=False, repr=False)
    _stop: threading.Event = field(init=False, repr=False)
    _thread: threading.Thread | None = field(init=False, default=None, repr=False)
    _latest: dict[str, ProviderHealth] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._latest = {provider: unknown_health(provider) for provider in STATUS_URLS}

    def poll_once(self) -> None:
        latest = {provider: self.fetch(provider) for provider in STATUS_URLS}
        with self._lock:
            self._latest = latest

    def snapshot(self) -> dict[str, ProviderHealth]:
        with self._lock:
            return dict(self._latest)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="provider-health", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=REQUEST_TIMEOUT_SECONDS * len(STATUS_URLS) + 1)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            # One second is the supported floor. It satisfies fast dashboards
            # without allowing a malformed zero interval to busy-loop against
            # public infrastructure.
            self._stop.wait(max(1.0, self.interval))
