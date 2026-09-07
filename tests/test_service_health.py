"""Provider status-page parsing and background-cache tests."""

from __future__ import annotations

from datetime import UTC, datetime

from agent_watch.service_health import HealthMonitor, HealthState, ProviderHealth, parse_summary

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


def _summary(*components: tuple[str, str], indicator: str = "none") -> dict:
    return {
        "status": {"indicator": indicator},
        "components": [{"name": name, "status": status} for name, status in components],
    }


def test_openai_relevant_components_are_online() -> None:
    health = parse_summary(
        "openai", _summary(("Responses", "operational"), ("Login", "operational")), now=NOW
    )
    assert health.state is HealthState.ONLINE
    assert health.checked_at == NOW


def test_anthropic_component_error_is_degraded() -> None:
    health = parse_summary(
        "anthropic",
        _summary(
            ("Claude Code", "degraded_performance"),
            ("Claude API (api.anthropic.com)", "operational"),
            indicator="minor",
        ),
        now=NOW,
    )
    assert health.state is HealthState.DEGRADED
    assert "Claude Code=degraded_performance" in health.detail


def test_missing_component_fails_closed() -> None:
    health = parse_summary("openai", _summary(("Responses", "operational")), now=NOW)
    assert health.state is HealthState.UNKNOWN


def test_monitor_replaces_its_memory_cache() -> None:
    def fetch(provider: str) -> ProviderHealth:
        return ProviderHealth(provider, HealthState.ONLINE, "ok", NOW)

    monitor = HealthMonitor(fetch=fetch)
    monitor.poll_once()
    assert {item.state for item in monitor.snapshot().values()} == {HealthState.ONLINE}
