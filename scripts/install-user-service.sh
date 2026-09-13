#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
UNIT_SOURCE="$PROJECT_ROOT/systemd/agent-while-true.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_TARGET="$UNIT_DIR/agent-while-true.service"
DROPIN_DIR="$UNIT_TARGET.d"
MANAGED_DROPIN="$DROPIN_DIR/10-agent-while-true-mode.conf"
MODE="observe"
ALLOW_CODEX_AUTO_RESUME=0
UNINSTALL=0

usage() {
    printf 'usage: %s [--auto [--allow-codex-auto-resume] | --uninstall]\n' "$0"
}

for argument in "$@"; do
    case "$argument" in
        --auto) MODE="auto" ;;
        --allow-codex-auto-resume) ALLOW_CODEX_AUTO_RESUME=1 ;;
        --uninstall) UNINSTALL=1 ;;
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

if [[ "$UNINSTALL" -eq 1 && "$#" -ne 1 ]]; then
    printf '%s\n' '--uninstall cannot be combined with another option.' >&2
    exit 2
fi
if [[ "$ALLOW_CODEX_AUTO_RESUME" -eq 1 && "$MODE" != "auto" ]]; then
    printf '%s\n' '--allow-codex-auto-resume requires --auto.' >&2
    exit 2
fi

if [[ "$UNINSTALL" -eq 1 ]]; then
    systemctl --user disable --now agent-while-true.service 2> /dev/null || true
    rm -f -- "$MANAGED_DROPIN"
    rmdir -- "$DROPIN_DIR" 2> /dev/null || true
    rm -f -- "$UNIT_TARGET"
    systemctl --user daemon-reload
    printf 'Removed %s\n' "$UNIT_TARGET"
    exit 0
fi
if [ ! -x "$HOME/.local/bin/agent-while-true" ]; then
    printf '%s\n' 'agent-while-true is not installed at ~/.local/bin/agent-while-true.' >&2
    printf '%s\n' 'Install it first: pipx install .' >&2
    exit 1
fi

install -d -m 700 -- "$UNIT_DIR"
install -m 644 -- "$UNIT_SOURCE" "$UNIT_TARGET"

if [[ "$MODE" == "auto" ]]; then
    install -d -m 700 -- "$DROPIN_DIR"
    temporary="$(mktemp "$UNIT_DIR/.agent-while-true-mode.XXXXXX")"
    trap 'rm -f -- "$temporary"' EXIT
    {
        printf '%s\n' '[Unit]'
        if [[ "$ALLOW_CODEX_AUTO_RESUME" -eq 1 ]]; then
            printf '%s\n' 'Description=Agent While True budget babysitter (auto, Codex enabled)'
        else
            printf '%s\n' 'Description=Agent While True budget babysitter (auto)'
        fi
        printf '\n'
        printf '%s\n' '[Service]'
        printf '%s\n' 'ExecStart='
        printf '%s\n' 'ExecStart=%h/.local/bin/agent-while-true run --auto --all --no-fzf'
        if [[ "$ALLOW_CODEX_AUTO_RESUME" -eq 1 ]]; then
            printf '%s\n' 'Environment=AGENT_WHILE_TRUE_ALLOW_CODEX_AUTO_RESUME=true'
        fi
    } > "$temporary"
    install -m 600 -- "$temporary" "$MANAGED_DROPIN"
    rm -f -- "$temporary"
    trap - EXIT
else
    rm -f -- "$MANAGED_DROPIN"
    rmdir -- "$DROPIN_DIR" 2> /dev/null || true
fi

systemctl --user daemon-reload
systemctl --user enable --now agent-while-true.service
printf 'Installed %s\n' "$UNIT_TARGET"
printf 'Enabled agent-while-true.service in %s mode.\n' "$MODE"
