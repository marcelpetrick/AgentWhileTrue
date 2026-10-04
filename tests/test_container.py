# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Safety and release-contract tests for the offline container artifact."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "scripts/container-entrypoint.sh"
SMOKE = ROOT / "scripts/container-smoke.sh"
PIPELINE = ROOT / "localPipeline.sh"
QUALITY_WORKFLOW = ROOT / ".github/workflows/quality.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"


def test_image_is_a_pinned_non_root_exact_wheel_simulator() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert (
        "python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016"
    ) in dockerfile
    assert "COPY dist/agent_while_true-${VERSION}-py3-none-any.whl /tmp/" in dockerfile
    assert "COPY dist/*.whl" not in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/agent-while-true-container"]' in dockerfile
    assert "container-simulate.py /usr/local/bin/agent-while-true-container-cli" in dockerfile
    assert "agent-while-true-container-cli" in dockerfile
    assert "container terminal automation is unsupported" in dockerfile
    for forbidden in ("apt-get", "--privileged", "/run/user", "/var/run/docker.sock"):
        assert forbidden not in dockerfile


def _fake_cli(tmp_path: Path) -> tuple[Path, Path]:
    capture = tmp_path / "arguments"
    cli = tmp_path / "agent-while-true"
    cli.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n', encoding="utf-8")
    cli.chmod(0o755)
    return cli, capture


def _entrypoint(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    cli, capture = _fake_cli(tmp_path)
    return subprocess.run(
        [str(ENTRYPOINT), *arguments],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "AGENT_WHILE_TRUE_CONTAINER_CLI": str(cli),
            "CAPTURE": str(capture),
        },
    )


def test_container_defaults_to_every_offline_simulation(tmp_path: Path) -> None:
    result = _entrypoint(tmp_path)

    assert result.returncode == 0
    assert (tmp_path / "arguments").read_text(encoding="utf-8") == "simulate\n--all\n"


@pytest.mark.parametrize(
    "arguments",
    [("simulate", "agent-exited"), ("--version",), ("--help",), ("-h",)],
)
def test_container_exposes_only_offline_cli_surfaces(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    result = _entrypoint(tmp_path, *arguments)

    assert result.returncode == 0
    assert (tmp_path / "arguments").read_text(encoding="utf-8") == "".join(
        f"{argument}\n" for argument in arguments
    )


@pytest.mark.parametrize(
    "command",
    ["run", "status", "quota", "doctor", "init", "config", "logs", "summary"],
)
def test_container_refuses_every_host_facing_command(tmp_path: Path, command: str) -> None:
    result = _entrypoint(tmp_path, command)

    assert result.returncode == 64
    assert "Container terminal supervision is unsupported" in result.stderr
    assert not (tmp_path / "arguments").exists()


def test_smoke_runs_the_image_without_host_access() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")

    for guard in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs /tmp:rw,nosuid,nodev,noexec,size=32m",
    ):
        assert guard in smoke
    for forbidden in ("--privileged", "--pid=host", "/run/user", "/var/run/docker.sock"):
        assert forbidden not in smoke
    assert "run --auto --all --once" in smoke
    assert 'refusal_status" -ne 64' in smoke


def test_pipeline_has_explicit_auto_require_and_skip_modes_after_the_wheel() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")

    assert 'CONTAINER_MODE="${AGENT_WHILE_TRUE_CONTAINER:-auto}"' in pipeline
    assert "auto | require | skip" in pipeline
    assert pipeline.index('PIPELINE_RESULTS+=("Package build') < pipeline.index(
        "scripts/container-smoke.sh"
    )
    assert 'CONTAINER_MODE" == "require"' in pipeline


def test_container_sources_ship_in_the_source_archive() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "Dockerfile .dockerignore" in manifest
    assert "recursive-include .github/workflows *.yml" in manifest
    assert "recursive-include scripts *.py *.sh" in manifest


def test_quality_requires_the_image_only_on_python_3_12() -> None:
    workflow = QUALITY_WORKFLOW.read_text(encoding="utf-8")

    assert '- python: "3.12"\n            container: require' in workflow
    assert workflow.count("container: skip") == 2
    assert "AGENT_WHILE_TRUE_CONTAINER: ${{ matrix.container }}" in workflow


def test_release_is_tag_only_multiarch_and_attested() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert 'tags:\n      - "agentwhiletrue-v*"' in workflow
    assert "workflow_dispatch" not in workflow
    assert "IMAGE_NAME: marcelpetrick/agent-while-true" in workflow
    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert "sbom: true" in workflow
    assert "provenance: mode=max" in workflow
    assert "push-to-registry: true" in workflow
    assert workflow.index("Verify release tag") < workflow.index("Log in to GHCR")
    assert workflow.index("Run canonical local pipeline") < workflow.index("Log in to GHCR")


def test_every_workflow_action_is_pinned_to_a_full_sha() -> None:
    for path in (QUALITY_WORKFLOW, RELEASE_WORKFLOW):
        workflow = path.read_text(encoding="utf-8")
        references = re.findall(r"^\s*uses:\s+\S+@([^\s]+)", workflow, flags=re.MULTILINE)
        assert references
        assert all(re.fullmatch(r"[0-9a-f]{40}", reference) for reference in references)
