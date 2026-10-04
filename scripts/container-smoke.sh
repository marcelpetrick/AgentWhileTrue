#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Build and exercise the official offline-simulation image. No host namespace,
# socket, credential or network is exposed to the running container.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
PYTHON_BIN="${PYTHON:-python3}"
CONTAINER_ENGINE="${AGENT_WHILE_TRUE_CONTAINER_ENGINE:-docker}"

if [ "$#" -ne 0 ]; then
    printf 'usage: %s\n' "$0" >&2
    exit 2
fi
if ! command -v "$CONTAINER_ENGINE" > /dev/null 2>&1; then
    printf 'container engine not found: %s\n' "$CONTAINER_ENGINE" >&2
    exit 1
fi
if ! "$CONTAINER_ENGINE" info > /dev/null 2>&1; then
    printf 'container engine is not reachable: %s\n' "$CONTAINER_ENGINE" >&2
    exit 1
fi

cd -- "$PROJECT_ROOT"
version="$(PYTHONPATH=src "$PYTHON_BIN" -c \
    'from agent_while_true.version import __version__; print(__version__)')"
wheel="dist/agent_while_true-${version}-py3-none-any.whl"
if [ ! -f "$wheel" ]; then
    printf 'verified wheel not found: %s\n' "$wheel" >&2
    exit 1
fi

revision="$(git rev-parse HEAD 2> /dev/null || printf unknown)"
created="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
image="agent-while-true-smoke:${version}"

"$CONTAINER_ENGINE" build \
    --build-arg "VERSION=$version" \
    --build-arg "REVISION=$revision" \
    --build-arg "CREATED=$created" \
    --tag "$image" \
    .

run_image() {
    "$CONTAINER_ENGINE" run --rm \
        --network=none \
        --read-only \
        --cap-drop=ALL \
        --security-opt=no-new-privileges \
        --tmpfs /tmp:rw,nosuid,nodev,noexec,size=32m \
        "$image" "$@"
}

config_user="$("$CONTAINER_ENGINE" image inspect --format '{{.Config.User}}' "$image")"
if [ "$config_user" != "10001:10001" ]; then
    printf 'container user is %s, expected 10001:10001\n' "$config_user" >&2
    exit 1
fi

reported="$(run_image --version)"
if [ "$reported" != "Agent While True $version" ]; then
    printf 'container version mismatch: %s\n' "$reported" >&2
    exit 1
fi

scenario_output="$(run_image)"
expected_scenarios="$(PYTHONPATH=src "$PYTHON_BIN" -c \
    'from agent_while_true.simulate import SCENARIOS; print(len(SCENARIOS))')"
passed_scenarios="$(grep -Ec '^[a-z0-9-]+[[:space:]]+PASS$' <<< "$scenario_output")"
if [ "$passed_scenarios" -ne "$expected_scenarios" ] \
    || grep -Eq '^[a-z0-9-]+[[:space:]]+FAIL$' <<< "$scenario_output"; then
    printf '%s\n' "$scenario_output" >&2
    printf 'container scenarios: %s passed, expected %s\n' \
        "$passed_scenarios" "$expected_scenarios" >&2
    exit 1
fi

set +e
refusal="$(run_image run --auto --all --once 2>&1)"
refusal_status=$?
set -e
if [ "$refusal_status" -ne 64 ] \
    || [[ "$refusal" != *"Container terminal supervision is unsupported"* ]]; then
    printf 'operational command was not refused safely (exit %s):\n%s\n' \
        "$refusal_status" "$refusal" >&2
    exit 1
fi

runtime_probe="$("$CONTAINER_ENGINE" run --rm \
    --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --entrypoint python "$image" -c \
    'import os, shutil; print(os.geteuid(), shutil.which("qdbus"), shutil.which("qdbus6"))')"
if [ "$runtime_probe" != "10001 None None" ]; then
    printf 'unsafe runtime probe result: %s\n' "$runtime_probe" >&2
    exit 1
fi

label_version="$("$CONTAINER_ENGINE" image inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$image")"
label_license="$("$CONTAINER_ENGINE" image inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.licenses"}}' "$image")"
if [ "$label_version" != "$version" ] || [ "$label_license" != "GPL-3.0-or-later" ]; then
    printf 'container OCI labels do not match the package\n' >&2
    exit 1
fi

printf 'container smoke passed: %s (%s scenarios, non-root, offline-only)\n' \
    "$image" "$passed_scenarios"
