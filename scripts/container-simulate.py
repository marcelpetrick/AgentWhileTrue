#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run the fake-world CLI surfaces without inheriting the image environment."""

from __future__ import annotations

import sys

from agent_while_true import classify
from agent_while_true.cli import main

# The scenario harness supplies fake processes, terminals, clocks and quota.
# Docker's own marker files must not reclassify those invented processes. This
# launcher is reachable only through the entrypoint's offline-command allowlist;
# the installed CLI and every real supervision path keep the normal blockers.
classify._CONTAINER_CGROUP_MARKERS = ()
classify._CONTAINER_FILES = ()

raise SystemExit(main(sys.argv[1:]))
