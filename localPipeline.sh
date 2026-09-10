#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
declare -a PIPELINE_RESULTS=()
TEMP_ROOT=""

usage() {
    cat <<'EOF'
Usage: ./localPipeline.sh [--noRun]

Runs the same complete gate used by GitHub Actions:
  1. Verify Python 3.12+
  2. Ruff lint and format check, ShellCheck, tests and coverage
  3. Run every safety simulation
  4. Build the source distribution and wheel
  5. Install the wheel in an isolated environment
  6. Smoke-test both command names, doctor, status, quota, and all simulations

--noRun is accepted for consistency with this repository's other local
pipelines. Agent While True has no final interactive launch, so it is a no-op.
EOF
}

for argument in "$@"; do
    case "$argument" in
        --noRun | --no-run) ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            printf 'unknown option: %s\n' "$argument" >&2
            usage >&2
            exit 2
            ;;
    esac
done

cleanup() {
    if [[ -n "$TEMP_ROOT" && -d "$TEMP_ROOT" ]]; then
        rm -rf -- "$TEMP_ROOT"
    fi
}

smoke_command() {
    local output status
    set +e
    output="$("$@" 2>&1)"
    status=$?
    set -e
    if [[ "$status" -gt 1 || "$output" == *Traceback* ]]; then
        printf '%s\n' "$output" >&2
        return 1
    fi
}

finish() {
    local status=$?
    printf '\n========== Agent While True Pipeline =========='
    printf '\n'
    for result in "${PIPELINE_RESULTS[@]}"; do
        printf '%s\n' "$result"
    done
    if [[ "$status" -eq 0 ]]; then
        printf 'Overall          : PASS\n'
    else
        printf 'Overall          : FAIL (exit %d)\n' "$status" >&2
    fi
    printf '================================================\n'
    cleanup
}

trap finish EXIT
cd -- "$PROJECT_ROOT"

printf '[INFO] Project root: %s\n' "$PROJECT_ROOT"
"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required, found {sys.version.split()[0]}")
print(f"[INFO] Python {sys.version.split()[0]}")
PY
PIPELINE_RESULTS+=("Python baseline  : PASS (3.12+)")

scripts/quality.sh
PIPELINE_RESULTS+=("Quality gate     : PASS (Ruff, format, ShellCheck, pytest coverage)")

PYTHONPATH=src "$PYTHON_BIN" -m agent_watch.cli simulate --all
PIPELINE_RESULTS+=("Safety scenarios : PASS (all)")

mkdir -p artifacts
"$PYTHON_BIN" scripts/profile_app.py --iterations 1 --profile artifacts/app.prof > artifacts/profile.txt
PIPELINE_RESULTS+=("Synthetic profile: PASS (privacy-safe workload)")

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/agent-while-true-pipeline.XXXXXX")"
ARTIFACT_DIR="$TEMP_ROOT/dist"
"$PYTHON_BIN" -m build --outdir "$ARTIFACT_DIR"
mkdir -p dist
cp -- "$ARTIFACT_DIR"/* dist/
PIPELINE_RESULTS+=("Package build    : PASS (sdist and wheel)")

# Prove the shipped source, tests, scripts and licensing are usable without Git
# or files accidentally borrowed from the checkout.
mkdir -p "$TEMP_ROOT/source"
"$PYTHON_BIN" - "$ARTIFACT_DIR"/*.tar.gz "$TEMP_ROOT/source" <<'PY'
import sys
import tarfile

with tarfile.open(sys.argv[1]) as archive:
    archive.extractall(sys.argv[2], filter="data")
PY
source_roots=("$TEMP_ROOT/source"/*)
[[ "${#source_roots[@]}" -eq 1 ]]
(
    cd -- "${source_roots[0]}"
    unset PYTHONPATH
    scripts/quality.sh
)
PIPELINE_RESULTS+=("Source archive   : PASS (quality gate outside Git)")

"$PYTHON_BIN" scripts/sbom.py generate --wheel "$ARTIFACT_DIR"/*.whl \
    --sdist "$ARTIFACT_DIR"/*.tar.gz --output-dir dist/sbom
"$PYTHON_BIN" scripts/sbom.py validate --spdx dist/sbom/agent-while-true.spdx.json \
    --cyclonedx dist/sbom/agent-while-true.cdx.json
PIPELINE_RESULTS+=("Release SBOMs    : PASS (SPDX 2.3 and CycloneDX 1.6 validated)")

"$PYTHON_BIN" -m venv "$TEMP_ROOT/smoke"
"$TEMP_ROOT/smoke/bin/python" -m pip install --disable-pip-version-check --no-deps \
    "$ARTIFACT_DIR"/*.whl
expected_version="$(PYTHONPATH=src "$PYTHON_BIN" -c 'from agent_watch.version import __version__; print(__version__)')"
# Neither the checkout nor an inherited PYTHONPATH may satisfy these imports.
pushd "$TEMP_ROOT" > /dev/null
unset PYTHONPATH
[[ "$("$TEMP_ROOT/smoke/bin/agent-while-true" --version)" == *"$expected_version"* ]]
[[ "$("$TEMP_ROOT/smoke/bin/agent-watch" --version)" == *"$expected_version"* ]]
"$TEMP_ROOT/smoke/bin/agent-while-true" simulate --all
smoke_command "$TEMP_ROOT/smoke/bin/agent-while-true" doctor
smoke_command "$TEMP_ROOT/smoke/bin/agent-while-true" status
smoke_command "$TEMP_ROOT/smoke/bin/agent-while-true" quota
"$TEMP_ROOT/smoke/bin/agent-while-true" --log-file "$TEMP_ROOT/no-events.log" summary
"$TEMP_ROOT/smoke/bin/agent-watch" --log-file "$TEMP_ROOT/no-events.log" summary --days 7
PIPELINE_RESULTS+=("Installed wheel  : PASS (commands, diagnostics, simulations)")
popd > /dev/null
