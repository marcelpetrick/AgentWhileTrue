# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Agent While True: a conservative budget watch and babysitter for coding agents.

The package watches KDE Konsole sessions that are running Codex CLI or Claude
Code, recognises the provider-specific usage-limit prompts, and resumes a
blocked session only once every safety precondition holds. See ``docs/PLAN.md``
for the design and ``docs/vision.md`` for the product intent.
"""

from __future__ import annotations

import sys

if sys.version_info[:2] != (3, 14):  # pragma: no cover - this suite itself requires 3.14
    raise RuntimeError(f"Agent While True requires Python 3.14; found {sys.version.split()[0]}")

from agent_while_true.version import __version__

__all__ = ["__version__"]
