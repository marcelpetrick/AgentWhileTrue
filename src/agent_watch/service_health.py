"""Memory-only provider health from public, component-specific status APIs."""

from __future__ import annotations

import enum
import gzip
import http.client
import io
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

STATUS_URLS = {
    "openai": "https://status.openai.com/api/v2/summary.json",
    "anthropic": "https://status.claude.com/api/v2/summary.json",
}


@dataclass(frozen=True, slots=True)
class Component:
    """A stable status component, with its name retained as a migration fallback."""

    component_id: str
    name: str


WATCHED_COMPONENTS = {
    # Codex CLI uses the Codex service. Generic Responses and duplicate Login
    # components can report unrelated API or ChatGPT incidents.
    "openai": (Component("01KMP3KP5MGE23B80K1EK4S8PV", "Codex API"),),
    "anthropic": (
        Component("yyzkbfz2thpt", "Claude Code"),
        Component("k8w3r06qmzrp", "Claude API (api.anthropic.com)"),
    ),
}
REQUEST_TIMEOUT_SECONDS = 3.0
MAX_RESPONSE_BYTES = 128 * 1024
_STATUS_STATES = {
    "operational": 0,
    "under_maintenance": 1,
    "degraded_performance": 1,
    "partial_outage": 1,
    "major_outage": 2,
}


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


def _selected_components(provider: str, components: list[object]) -> list[tuple[str, str]] | None:
    records = [component for component in components if isinstance(component, dict)]
    selected: list[tuple[str, str]] = []
    for wanted in WATCHED_COMPONENTS[provider]:
        matches = [item for item in records if item.get("id") == wanted.component_id]
        if not matches:
            # Names are less stable than IDs, but allow a provider migration only
            # when the fallback is unambiguous. OpenAI currently has duplicate
            # Login names, which is why a unique-name requirement matters.
            matches = [item for item in records if item.get("name") == wanted.name]
        if len(matches) != 1:
            return None
        item = matches[0]
        name, status = item.get("name"), item.get("status")
        if not isinstance(name, str) or not isinstance(status, str):
            return None
        selected.append((name, status.casefold()))
    return selected


def parse_summary(provider: str, document: object, *, now: datetime) -> ProviderHealth:
    """Reduce a public summary to only the components used by the local CLI."""
    if provider not in WATCHED_COMPONENTS:
        return unknown_health(provider, "unsupported-provider")
    if not isinstance(document, dict):
        return unknown_health(provider, "malformed-status")
    components = document.get("components")
    if not isinstance(components, list):
        return unknown_health(provider, "missing-components")
    selected = _selected_components(provider, components)
    if selected is None:
        return unknown_health(provider, "component-not-found")
    if any(status not in _STATUS_STATES for _, status in selected):
        return unknown_health(provider, "unknown-component-status")
    severity = max(_STATUS_STATES[status] for _, status in selected)
    state = (HealthState.ONLINE, HealthState.DEGRADED, HealthState.OUTAGE)[severity]
    detail = ", ".join(f"{name}={status}" for name, status in selected)
    return ProviderHealth(provider, state, detail, now)


def _read_document(response: Any) -> object:
    compressed = response.read(MAX_RESPONSE_BYTES + 1)
    if len(compressed) > MAX_RESPONSE_BYTES:
        raise ValueError("status response too large")
    encoding = response.headers.get("Content-Encoding", "").casefold()
    if encoding == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            document_bytes = stream.read(MAX_RESPONSE_BYTES + 1)
    elif encoding in {"", "identity"}:
        document_bytes = compressed
    else:
        raise ValueError("unsupported status encoding")
    if len(document_bytes) > MAX_RESPONSE_BYTES:
        raise ValueError("status response too large")
    return json.loads(document_bytes)


@dataclass(slots=True)
class StatusPageClient:
    """Small conditional-GET client for one provider's public status page."""

    provider: str
    opener: Callable[..., Any] | None = None
    _etag: str | None = field(init=False, default=None, repr=False)
    _cached: ProviderHealth | None = field(init=False, default=None, repr=False)
    _connection: http.client.HTTPSConnection | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.opener is not None:
            return
        proxies = urllib.request.getproxies()
        if any(scheme in proxies for scheme in ("http", "https", "all")):
            # urllib applies the configured proxy and TLS behavior correctly.
            # This fallback cannot promise connection reuse, but connectivity
            # is more important than the direct-path optimization.
            self.opener = urllib.request.urlopen

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _persistent_response(self, headers: dict[str, str]) -> http.client.HTTPResponse:
        parsed = urlsplit(STATUS_URLS[self.provider])
        if self._connection is None:
            self._connection = http.client.HTTPSConnection(
                parsed.hostname,
                parsed.port,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        self._connection.request("GET", path, headers=headers)
        return self._connection.getresponse()

    def fetch(self, *, now: datetime | None = None) -> ProviderHealth:
        checked_at = now or datetime.now(UTC)
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "AgentWhileTrue service-health",
        }
        if self._etag:
            headers["If-None-Match"] = self._etag
        try:
            if self.opener is None:
                response_context = self._persistent_response(headers)
            else:
                request = urllib.request.Request(STATUS_URLS[self.provider], headers=headers)
                response_context = self.opener(request, timeout=REQUEST_TIMEOUT_SECONDS)
            with response_context as response:
                status = getattr(response, "status", 200)
                if status == 304 and self._cached is not None:
                    response.read(MAX_RESPONSE_BYTES + 1)
                    return replace(self._cached, checked_at=checked_at)
                if status != 200:
                    response.read(MAX_RESPONSE_BYTES + 1)
                    return unknown_health(self.provider, "status-unreachable")
                document = _read_document(response)
                etag = response.headers.get("ETag")
        except urllib.error.HTTPError as error:
            if error.code == 304 and self._cached is not None:
                return replace(self._cached, checked_at=checked_at)
            return unknown_health(self.provider, "status-unreachable")
        except (
            OSError,
            ValueError,
            http.client.HTTPException,
            urllib.error.URLError,
            json.JSONDecodeError,
        ):
            self.close()
            return unknown_health(self.provider, "status-unreachable")
        health = parse_summary(self.provider, document, now=checked_at)
        if health.state is not HealthState.UNKNOWN:
            self._cached = health
            self._etag = etag if isinstance(etag, str) else None
        return health


def fetch_summary(provider: str, *, now: datetime | None = None) -> ProviderHealth:
    """Perform one credential-free status request without retaining validators."""
    return StatusPageClient(provider).fetch(now=now)


@dataclass(slots=True)
class HealthMonitor:
    """Poll each status API independently and expose a tiny memory-only cache."""

    interval: float = 1.0
    fetch: Callable[[str], ProviderHealth] | None = None
    _lock: threading.Lock = field(init=False, repr=False)
    _stop: threading.Event = field(init=False, repr=False)
    _threads: list[threading.Thread] = field(init=False, default_factory=list, repr=False)
    _latest: dict[str, ProviderHealth] = field(init=False, repr=False)
    _clients: dict[str, StatusPageClient] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._latest = {provider: unknown_health(provider) for provider in STATUS_URLS}
        self._clients = {provider: StatusPageClient(provider) for provider in STATUS_URLS}

    def _fetch(self, provider: str) -> ProviderHealth:
        if self.fetch is not None:
            return self.fetch(provider)
        return self._clients[provider].fetch()

    def _poll_provider(self, provider: str) -> None:
        health = self._fetch(provider)
        with self._lock:
            self._latest[provider] = health

    def poll_once(self) -> None:
        for provider in STATUS_URLS:
            self._poll_provider(provider)

    def snapshot(self) -> dict[str, ProviderHealth]:
        with self._lock:
            return dict(self._latest)

    def start(self) -> None:
        if self._threads:
            return
        for provider in STATUS_URLS:
            thread = threading.Thread(
                target=self._run_provider,
                args=(provider,),
                name=f"provider-health-{provider}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=REQUEST_TIMEOUT_SECONDS + 1)
        for client in self._clients.values():
            client.close()

    def _run_provider(self, provider: str) -> None:
        while not self._stop.is_set():
            self._poll_provider(provider)
            # One second is the supported floor: responsive without busy-looping.
            self._stop.wait(max(1.0, self.interval))
