"""Provider status-page parsing, transport, and background-cache tests."""

from __future__ import annotations

import gzip
import io
import json
import urllib.error
from datetime import UTC, datetime

from agent_watch.service_health import (
    HealthMonitor,
    HealthState,
    ProviderHealth,
    StatusPageClient,
    parse_summary,
)

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 8, 10, 0, 1, tzinfo=UTC)


def _component(component_id: str, name: str, status: str) -> dict[str, str]:
    return {"id": component_id, "name": name, "status": status}


def _summary(*components: dict[str, str], indicator: str = "none") -> dict:
    return {"status": {"indicator": indicator}, "components": list(components)}


def test_openai_uses_codex_component_not_generic_overall_status() -> None:
    health = parse_summary(
        "openai",
        _summary(
            _component("01KMP3KP5MGE23B80K1EK4S8PV", "Codex API", "operational"),
            _component("other", "Responses", "major_outage"),
            indicator="critical",
        ),
        now=NOW,
    )
    assert health.state is HealthState.ONLINE
    assert health.detail == "Codex API=operational"
    assert health.checked_at == NOW


def test_component_id_survives_display_name_change() -> None:
    health = parse_summary(
        "openai",
        _summary(_component("01KMP3KP5MGE23B80K1EK4S8PV", "Codex CLI/API", "major_outage")),
        now=NOW,
    )
    assert health.state is HealthState.OUTAGE
    assert health.detail == "Codex CLI/API=major_outage"


def test_anthropic_code_or_api_problem_is_degraded() -> None:
    health = parse_summary(
        "anthropic",
        _summary(
            _component("yyzkbfz2thpt", "Claude Code", "degraded_performance"),
            _component("k8w3r06qmzrp", "Claude API (api.anthropic.com)", "operational"),
        ),
        now=NOW,
    )
    assert health.state is HealthState.DEGRADED
    assert "Claude Code=degraded_performance" in health.detail


def test_unique_name_fallback_handles_component_id_migration() -> None:
    health = parse_summary(
        "openai",
        _summary(_component("replacement", "Codex API", "operational")),
        now=NOW,
    )
    assert health.state is HealthState.ONLINE


def test_ambiguous_or_missing_component_fails_closed() -> None:
    duplicated = _summary(
        _component("one", "Codex API", "operational"),
        _component("two", "Codex API", "operational"),
    )
    assert parse_summary("openai", duplicated, now=NOW).state is HealthState.UNKNOWN
    assert parse_summary("openai", _summary(), now=NOW).state is HealthState.UNKNOWN


def test_unknown_component_status_fails_closed() -> None:
    health = parse_summary(
        "openai",
        _summary(_component("01KMP3KP5MGE23B80K1EK4S8PV", "Codex API", "new_status")),
        now=NOW,
    )
    assert health.state is HealthState.UNKNOWN
    assert health.detail == "unknown-component-status"


class _Response(io.BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str], *, status: int = 200) -> None:
        super().__init__(body)
        self.headers = headers
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def test_client_uses_gzip_and_etag_conditional_requests() -> None:
    document = _summary(_component("01KMP3KP5MGE23B80K1EK4S8PV", "Codex API", "operational"))
    responses: list[object] = [
        _Response(
            gzip.compress(json.dumps(document).encode()),
            {"Content-Encoding": "gzip", "ETag": 'W/"one"'},
        ),
        urllib.error.HTTPError("url", 304, "Not Modified", {}, None),
    ]
    requests = []

    def opener(request, *, timeout):
        assert timeout == 3.0
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    client = StatusPageClient("openai", opener=opener)
    assert client.fetch(now=NOW).state is HealthState.ONLINE
    cached = client.fetch(now=LATER)

    assert cached.state is HealthState.ONLINE
    assert cached.checked_at == LATER
    assert requests[0].get_header("Accept-encoding") == "gzip"
    assert requests[1].get_header("If-none-match") == 'W/"one"'


def test_client_rejects_oversized_or_unsupported_responses() -> None:
    oversized = _Response(b"x" * (128 * 1024 + 1), {})
    client = StatusPageClient("openai", opener=lambda *_args, **_kwargs: oversized)
    assert client.fetch(now=NOW).state is HealthState.UNKNOWN


def test_client_reuses_and_closes_persistent_connection(monkeypatch) -> None:
    document = _summary(_component("01KMP3KP5MGE23B80K1EK4S8PV", "Codex API", "operational"))
    connections = []

    class Connection:
        def __init__(self, host, port, *, timeout) -> None:
            assert host == "status.openai.com"
            assert port is None
            assert timeout == 3.0
            self.closed = False
            self.requests = []
            self.responses = [
                _Response(json.dumps(document).encode(), {"ETag": 'W/"one"'}),
                _Response(b"", {}, status=304),
            ]
            connections.append(self)

        def request(self, method, path, *, headers) -> None:
            self.requests.append((method, path, headers))

        def getresponse(self):
            return self.responses.pop(0)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("agent_watch.service_health.http.client.HTTPSConnection", Connection)
    client = StatusPageClient("openai")

    assert client.fetch(now=NOW).state is HealthState.ONLINE
    assert client.fetch(now=LATER).state is HealthState.ONLINE
    assert len(connections) == 1
    assert connections[0].requests[1][2]["If-None-Match"] == 'W/"one"'

    client.close()
    assert connections[0].closed


def test_monitor_replaces_each_memory_cache_entry() -> None:
    def fetch(provider: str) -> ProviderHealth:
        return ProviderHealth(provider, HealthState.ONLINE, "ok", NOW)

    monitor = HealthMonitor(fetch=fetch)
    monitor.poll_once()
    assert {item.state for item in monitor.snapshot().values()} == {HealthState.ONLINE}
