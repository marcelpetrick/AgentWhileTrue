<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Open issues and acceptance work

This is the single authoritative list of unresolved Agent While True work. It
consolidates the former root-level debugging and task documents. Completed
implementation plans remain under `docs/history/` as evidence, not as active
backlogs.

## Open acceptance issue

### O1 — Validate one natural provider reset end to end

Priority: critical acceptance evidence. Implementation status: complete in the
public v0.42.1 release; natural live acceptance remains outstanding.

The released build must supervise an intended Codex or Claude session through a
real quota exhaustion and reset, without fabricated quota data, process
replacement, unsafe input, or a paid/quality-changing choice. Acceptance needs
all of the following:

- run v0.42.1 or later in full-auto mode with only intended sessions selected;
- observe a supported, exact blocking prompt and a naturally eligible reset;
- confirm exactly one policy-approved continuation is sent;
- confirm the lifecycle is `PLANNED -> SENT -> VERIFIED`, or records an honest
  `FAILED` result without an unsafe duplicate;
- inspect the latest structured events with `agent-while-true logs -n 50` and
  verify they contain identifiers and pattern IDs, never terminal text, prompt
  content, credentials, tokens, email addresses, or environment values.

Correct refusal for stale, unknown, malformed, conflicting, or unsupported
evidence does not satisfy this acceptance item. It remains the correct runtime
behavior and must not be weakened merely to close the test.

## Known conservative boundaries

These are deliberate limits, not pending implementation bugs:

- A clock-only prompt first observed after its apparent reset cannot be dated
  retroactively unless persisted first-sighting or corroborating absolute quota
  evidence exists. The supervisor refuses instead of guessing a date.
- A persisted `PLANNED` action left across an ambiguous crash window is not
  automatically repeated. It needs human inspection because the terminal API
  cannot prove whether input reached the process.
- KDE Konsole exposes no atomic compare-screen-and-send operation. Agent While
  True minimizes the remaining race by making the last external check a fresh
  process-identity read and performing no persistence between it and `sendText`.
- Unsupported terminals, SSH, containers, tmux/screen, unknown prompt shapes,
  purchases, paid credits, upgrades, reset credits, and model downgrades remain
  intentionally outside automation.

## Resolved debugging issues

The former D1–D8 incident report is summarized here so old failures are not
mistaken for current work:

| ID | Resolution in v0.42.x |
| --- | --- |
| D1 | Clock-only resets are anchored to first sighting or corroborated absolute evidence. |
| D2 | The freshest valid windowed quota event is selected across same-profile open Codex rollouts. |
| D3 | Explicitly opted-in Codex sessions may use bounded timed trials after an anchored reset; quota remains unknown/stale when it is unknown/stale. |
| D4 | A printed future reset gates Codex input even when an older quota sample says available. |
| D5 | Waiting sessions continue to be observed so manual recovery becomes visible. |
| D6 | A process-bound eleven-attempt episode budget persists across screen changes and restarts. |
| D7 | Retry lifecycle logs identify provider, session, process, episode, and attempt. |
| D8 | Claude recognition is scoped to the active prompt region and ignores logged paid-pattern identifiers while retaining real paid-choice vetoes. |

Regression coverage includes changed fingerprints, restart recovery, the full
retry budget, final revalidation cancellation, stale/fresh quota conflicts, and
Claude log-text false positives. The v0.42.1 release passed 549 tests on Python
3.12, 3.13, and 3.14, the live read-only Konsole integration check, the full
packaging pipeline, SPDX/CycloneDX validation, and the hosted dependency audit.

## Maintenance triggers

New issues belong in this file only when evidence makes them actionable:

- changed provider prompt or quota schema: capture a redacted real fixture and
  add the failing regression before changing recognition;
- changed Konsole D-Bus behavior: reproduce with `doctor` and the opt-in live
  adapter test without sending a real continuation;
- failed or duplicate live action: preserve privacy-safe lifecycle identifiers,
  add a deterministic regression, and fix the smallest responsible layer;
- coverage regression: restore the enforced 91% combined floor with meaningful
  failure-path tests, prioritizing process classification and Konsole errors;
- dependency advisory: update the exact development/build pin and run the full
  source, wheel, audit, and SBOM gates.

Remove an item from the open section only when its stated evidence exists. Keep
the resolution in the changelog or history rather than allowing this file to
grow into another archive.
