# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for layered configuration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agent_while_true import config as config_module
from agent_while_true.config import Config, ConfigError, Mode, load, parse_bool, parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("60", 60.0), ("60s", 60.0), ("90s", 90.0), ("2m", 120.0), ("1h", 3600.0), ("500ms", 0.5)],
)
def test_parse_duration(text: str, seconds: float) -> None:
    assert parse_duration(text) == seconds


def test_parse_duration_rejects_nonsense() -> None:
    with pytest.raises(ConfigError):
        parse_duration("soon")


@pytest.mark.parametrize("text", ["1", "true", "YES", "on"])
def test_parse_bool_true(text: str) -> None:
    assert parse_bool(text) is True


def test_parse_bool_rejects_nonsense() -> None:
    with pytest.raises(ConfigError):
        parse_bool("maybe")


def test_defaults_are_conservative() -> None:
    config = Config()
    assert config.mode is Mode.ASK
    assert config.reset_grace == 60.0
    assert config.policy.resume_after_reset
    assert not config.policy.auto_use_paid_credits
    assert not config.policy.auto_buy_credits
    assert not config.policy.auto_accept_model_downgrade
    assert not config.policy.auto_consume_reset_credit
    assert not config.policy.allow_codex_auto_resume
    assert not config.allow_root


def test_config_file_is_parsed_not_executed(tmp_path: Path) -> None:
    path = tmp_path / "config"
    path.write_text(
        "# a comment\n"
        "\n"
        'LOG_FILE="$HOME/logs/watch.log"\n'
        "RESET_GRACE=90s\n"
        "MODE=observe\n"
        "AUTO_BUY_CREDITS=false\n"
    )
    config = load(config_path=path, environ={})
    assert config.reset_grace == 90.0
    assert config.mode is Mode.OBSERVE
    assert str(config.log_file).endswith("/logs/watch.log")


def test_unknown_setting_is_an_error_not_a_silent_default(tmp_path: Path) -> None:
    path = tmp_path / "config"
    path.write_text("RESET_GRACEE=90\n")
    with pytest.raises(ConfigError, match="unknown setting"):
        load(config_path=path, environ={})


def test_malformed_line_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "config"
    path.write_text("this is not a setting\n")
    with pytest.raises(ConfigError, match="expected KEY=VALUE"):
        load(config_path=path, environ={})


def test_environment_overrides_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config"
    path.write_text("RESET_GRACE=90\n")
    config = load(config_path=path, environ={"AGENT_WHILE_TRUE_RESET_GRACE": "5m"})
    assert config.reset_grace == 300.0


def test_cli_overrides_the_environment(tmp_path: Path) -> None:
    path = tmp_path / "config"
    path.write_text("RESET_GRACE=90\n")
    config = load(
        config_path=path,
        environ={"AGENT_WHILE_TRUE_RESET_GRACE": "5m"},
        overrides={"reset_grace": "10"},
    )
    assert config.reset_grace == 10.0


def test_unrelated_environment_variables_are_ignored() -> None:
    # A bare MODE in the environment must not reconfigure the supervisor.
    config = load(config_path=Path("/nonexistent"), environ={"MODE": "auto"})
    assert config.mode is Mode.ASK


def test_retry_delays_parse_as_a_list() -> None:
    config = load(
        config_path=Path("/nonexistent"),
        environ={"AGENT_WHILE_TRUE_RETRY_DELAYS": "5s, 30s, 60s"},
    )
    assert config.retry_delays == (5.0, 30.0, 60.0)


def test_retry_delay_clamps_to_the_last_entry() -> None:
    config = Config()
    assert config.retry_delay(1) == 5.0
    assert config.retry_delay(3) == 60.0
    assert config.retry_delay(99) == 60.0
    assert config.retry_delay(0) == 0.0


def test_observe_mode_may_not_send_input() -> None:
    assert not Mode.OBSERVE.may_send_input
    assert Mode.ASK.may_send_input
    assert Mode.AUTO.may_send_input


def test_runtime_dir_falls_back_to_state_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert config_module.default_runtime_dir() == tmp_path / "agent-while-true"


def test_describe_lists_policy_and_resolved_paths() -> None:
    rows = dict(config_module.describe(Config()))
    assert rows["mode"] == "ask"
    assert rows["policy.auto_buy_credits"] == "False"
    assert rows["resolved_log_file"].endswith("agent-while-true.log")


@pytest.mark.parametrize("delays", [(), (float("inf"),), (-1.0,), (86401.0,), (1.0,) * 33])
def test_retry_delays_must_be_finite_and_bounded(delays) -> None:
    """``retry_delay`` indexes this tuple directly; an empty one raises there."""
    with pytest.raises(ConfigError, match="RETRY_DELAYS"):
        replace(Config(), retry_delays=delays)


@pytest.mark.parametrize("attempts", [-5, 1001, 1.5])
def test_max_resume_attempts_must_be_a_sane_whole_number(attempts) -> None:
    with pytest.raises(ConfigError, match="MAX_RESUME_ATTEMPTS"):
        replace(Config(), max_resume_attempts=attempts)


def test_an_empty_retry_delays_setting_is_rejected_at_load() -> None:
    with pytest.raises(ConfigError, match="RETRY_DELAYS"):
        load(config_path=None, environ={"AGENT_WHILE_TRUE_RETRY_DELAYS": ""})


def test_every_configured_attempt_has_a_delay() -> None:
    config = Config()
    for attempt in range(config.max_resume_attempts + 2):
        assert config.retry_delay(attempt) >= 0.0


@pytest.mark.parametrize("interval", [0.0, -1.0, 86401.0])
def test_service_status_interval_must_be_a_usable_period(interval) -> None:
    """A zero or negative value was silently floored back to one request a second."""
    with pytest.raises(ConfigError, match="SERVICE_STATUS_INTERVAL"):
        replace(Config(), service_status_interval=interval)


def test_the_configured_status_interval_is_the_one_actually_waited() -> None:
    config = Config(service_status_interval=300.0)
    assert max(1.0, config.service_status_interval) == config.service_status_interval
