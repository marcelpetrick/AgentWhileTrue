#!/bin/sh

# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

# This image demonstrates the fake-terminal safety scenarios. Running the
# supervisor in a container would invalidate its host PID, TTY and D-Bus
# assumptions, so the official entrypoint exposes no operational command.
set -eu

CLI="${AGENT_WHILE_TRUE_CONTAINER_CLI:-/usr/local/bin/agent-while-true-container-cli}"

if [ "$#" -eq 0 ]; then
    set -- simulate --all
fi

case "$1" in
    simulate | --version | --help | -h)
        exec "$CLI" "$@"
        ;;
    *)
        printf '%s\n' \
            'The official container is an offline safety-simulation artifact.' \
            'Container terminal supervision is unsupported; install Agent While True on the KDE host.' \
            >&2
        exit 64
        ;;
esac
