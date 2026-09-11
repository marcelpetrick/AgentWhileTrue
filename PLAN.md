<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Agent While True implementation plan

This plan tracks the current implementation and the work that remains. Product
intent and safety requirements live in [vision.md](vision.md); implemented
structure and data flows live in [ARCHITECTURE.md](ARCHITECTURE.md); the one
remaining machine-level validation is detailed in [todo.md](todo.md).

## Current status

Agent While True is a working standalone Python 3.12+ package for KDE Konsole on
Linux. It has no third-party runtime dependencies. The repository is released
through an atomic, versioned commit history and a GitHub quality matrix covering
Python 3.12, 3.13, and 3.14.

The requested implementation is complete:

- Konsole sessions are discovered through D-Bus and bound to service, session,
  PID, process start time, and TTY.
- Codex and Claude processes are classified through `/proc`; SSH, containers,
  tmux/screen, shells, ambiguity, and replacement processes fail closed.
- Provider prompt adapters recognize only tested prompt shapes and veto paid,
  upgrade, reset-credit, and quality-changing choices.
- Codex quota is read from its local rollout stream and bound to a validated
  account/rate-limit identity.
- Claude quota is projected by the owner-only status-line bridge.
- Five-hour and weekly usage meters show compact reset countdowns.
- Official Codex API and Claude Code/API status components are polled
  independently once per second with bounded, compressed, conditional requests.
- Observe, ask, and full-auto modes share the same supervisor and policy gate;
  uppercase `A` deliberately toggles observe/full-auto in the TUI.
- The action lifecycle is persisted as `PLANNED -> SENT -> VERIFIED|FAILED` and
  the TUI retains the latest 50 privacy-preserving history entries.
- The single-instance lock permits at most one input-capable watcher.
- Deterministic simulations, package smoke tests, and a live read-only Konsole
  adapter test are part of the release gate.
- Resume explanations, saved presentation preferences, day/week operational
  summaries, and a responsive scrolling dashboard are implemented; the ordered
  feature plan and validation notes are in [nextFeatures.md](nextFeatures.md).
- Measured performance, coverage, licensing and dual-format SBOM gates are
  recorded in [maturityPlan.md](maturityPlan.md). The observed retry and Claude
  prompt fixes are tracked in [retryFixPlan.md](retryFixPlan.md).

## Remaining acceptance gate

No known feature implementation is pending. Project-level acceptance remains
open until one naturally occurring, eligible quota reset proves the final
end-to-end action on a real provider session:

1. Leave the current version running in full-auto mode with intended sessions
   selected.
2. Allow a supported session to reach a genuine quota limit and reset without
   manually changing its process, prompt, or quota state.
3. Confirm exactly one continuation occurs after the reset grace period.
4. Inspect `agent-while-true logs -n 50` for the matching
   `PLANNED -> SENT -> VERIFIED` lifecycle, or a truthful `FAILED` result.
5. Confirm the log contains identifiers and pattern IDs only, never terminal
   text, prompt content, credentials, or environment values.

This gate must not be forced with a paid choice, model downgrade, fabricated
provider state, or input to an unrelated live session. Simulated reset tests
remain the deterministic regression mechanism.

## Maintenance plan

Maintenance is evidence-driven rather than scheduled feature growth.

| Trigger | Required response |
| --- | --- |
| Codex or Claude changes a blocking prompt | Capture a real redacted fixture, add a failing recognition test, then update the narrow adapter pattern. |
| Provider quota schema changes | Preserve old valid data until stale, reject malformed/new ambiguity, and add parser fixtures before adapting. |
| Provider status component identity changes | Verify the official public JSON document, update exact IDs, and retain `UNKNOWN` on mismatch. |
| Konsole changes its D-Bus contract | Re-run `doctor` and the opt-in adapter test; do not weaken identity or prompt revalidation. |
| A dependency release is considered | Keep exact development/build pins, verify stable upstream releases, and run the complete pipeline. |
| A live action fails or duplicates | Preserve evidence without terminal contents, add a deterministic lifecycle regression, then fix the smallest responsible layer. |

## Delivery plan for every change

1. Inspect the worktree and preserve unrelated user changes.
2. Make one logical change with tests or evidence proportional to its risk.
3. Bump `src/agent_watch/version.py` and add the newest matching
   `CHANGELOG.md` section.
4. Run the required pre-commit checks:

   ```bash
   ruff check .
   ruff format --check .
   shellcheck --severity=style scripts/*.sh
   python3 -m pytest -q
   git diff --check
   ```

5. Commit with the established conventional subject style.
6. Before pushing or tagging, run `./localPipeline.sh`, all CLI diagnostics and
   simulations, and the opt-in live Konsole test when KDE Konsole is available.
7. Build and install the wheel in isolation; smoke-test both command names.
8. Push only when requested. Tag only a fully verified release and confirm both
   GitHub workflows and published artifacts.

## Deferred scope

The following remain intentionally outside the current product:

- non-KDE terminal automation;
- nested tmux/screen, SSH, container, or root automation;
- paid credit use, purchases, subscription changes, upgrades, reset credits,
  or automatic model downgrades;
- heuristic interpretation of unknown prompts;
- bypassing provider limits or manufacturing quota availability;
- a daemon protocol, web service, or remote control plane;
- predictive capacity estimates without an official source.

Future terminal or provider support must enter through the existing adapter
boundaries and preserve the same identity, quota, prompt, policy, persistence,
and immediate-revalidation gates.
