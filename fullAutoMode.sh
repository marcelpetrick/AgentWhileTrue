#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SYSTEM_PYTHON="${PYTHON:-python3}"
RUN_INTERFACE=1

usage() {
    cat <<'EOF'
Usage: ./fullAutoMode.sh [--noRun]

Builds and launches a verified Agent While True installation:
  1. Require the normal desktop user, Python 3.12+, and pipx
  2. Prepare isolated development tools in .venv
  3. Run the complete local release pipeline
  4. Install the newly built wheel with pipx
  5. Create the default config if it does not exist
  6. Require a passing environment doctor and show live status/quota
  7. Open the auto-mode dashboard for every eligible agent session

Codex auto-resume is explicitly enabled by this full-auto entry point. Paid,
upgrade, reset-credit, and model-downgrade actions remain forbidden.

If another input-capable watcher is already running, it is left untouched and
this script opens an observe-only dashboard alongside it.

--noRun, --no-run  Complete setup and checks without opening the dashboard.
EOF
}

for argument in "$@"; do
    case "$argument" in
        --noRun | --no-run) RUN_INTERFACE=0 ;;
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

if [[ "$EUID" -eq 0 ]]; then
    printf '%s\n' 'fullAutoMode.sh must run as the KDE desktop user, not as root.' >&2
    exit 1
fi
if ! command -v "$SYSTEM_PYTHON" > /dev/null 2>&1; then
    printf 'missing Python executable: %s\n' "$SYSTEM_PYTHON" >&2
    exit 1
fi
if ! command -v pipx > /dev/null 2>&1; then
    printf '%s\n' 'pipx is required. On Manjaro/Arch, install the python-pipx package.' >&2
    exit 1
fi

cd -- "$PROJECT_ROOT"
"$SYSTEM_PYTHON" - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required, found {sys.version.split()[0]}")
PY

printf '%s\n' '[1/6] Preparing isolated development tools'
"$SYSTEM_PYTHON" -m venv "$PROJECT_ROOT/.venv"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
"$VENV_PYTHON" -m pip install --disable-pip-version-check -e '.[dev]'

printf '\n%s\n' '[2/6] Running the complete release gate'
PATH="$PROJECT_ROOT/.venv/bin:$PATH" PYTHON="$VENV_PYTHON" ./localPipeline.sh --noRun

version="$(PYTHONPATH=src "$VENV_PYTHON" -c \
    'from agent_watch.version import __version__; print(__version__)')"
wheel="$PROJECT_ROOT/dist/agent_while_true-$version-py3-none-any.whl"
if [[ ! -f "$wheel" ]]; then
    printf 'verified wheel was not produced: %s\n' "$wheel" >&2
    exit 1
fi

printf '\n%s\n' '[3/6] Installing the verified wheel with pipx'
# pipx's uv backend otherwise refuses to replace its own existing environment.
# This affects only the named Agent While True venv created by pipx.
UV_VENV_CLEAR=1 pipx install --force "$wheel"

pipx_bin_dir="${PIPX_BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
cli="$pipx_bin_dir/agent-while-true"
if [[ ! -x "$cli" ]]; then
    cli="$(command -v agent-while-true || true)"
fi
if [[ -z "$cli" || ! -x "$cli" ]]; then
    printf '%s\n' 'pipx installed Agent While True, but its executable is not reachable.' >&2
    printf '%s\n' 'Run pipx ensurepath, start a new shell, and try again.' >&2
    exit 1
fi

printf '\n%s\n' '[4/6] Initializing configuration and checking the environment'
"$cli" init
doctor_output="$("$cli" doctor)"
printf '%s\n' "$doctor_output"

printf '\n%s\n' '[5/6] Checking live sessions and provider quota'
"$cli" status
"$cli" quota

if [[ "$RUN_INTERFACE" -eq 0 ]]; then
    printf '\n%s\n' '[6/6] Dashboard launch skipped (--noRun)'
    exit 0
fi

if grep -Eq '^Single instance[[:space:]]+WARN' <<< "$doctor_output"; then
    printf '\n%s\n' '[6/6] An input controller is already running; opening the observe dashboard'
    exec "$cli" run --observe --all --no-fzf
fi

printf '\n%s\n' '[6/6] Opening the full auto-mode dashboard'
export AGENT_WATCH_ALLOW_CODEX_AUTO_RESUME=true
exec "$cli" run --auto --all --no-fzf
