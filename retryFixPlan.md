<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Live retry bug-fix plan (D1–D8)

The evidence and requested behavior are in [debugging.md](debugging.md).
Preserve its investigation commits on `debug/codex-retry`. The maturity and
performance work is complete at v0.41.0; apply these fixes as new logical commits.

1. Add regression fixtures for the reported Codex clock-only limit banner and
   Claude working-screen log text before changing recognition behavior.
2. D2: inspect all open Codex rollouts in the selected process tree and select
   the newest valid windowed quota evidence. Preserve account/profile isolation,
   bounded reads, stale/unknown semantics and immediate pre-action refresh.
3. D8: scope Claude paid-choice recognition to the actual active prompt/menu;
   preserve real paid-choice vetoes and the exact safe automatic-wait menu.
4. D1/D4/D5: anchor an unchanged blocking prompt's reset to its first sighting,
   prohibit early continuation even with pre-limit available quota, and observe
   waiting sessions independently of action deadlines so manual recovery appears.
5. D3/D6/D7: add the explicitly requested, opted-in Codex timed-retry exception.
   Unknown/stale quota stays unknown/stale; it is never relabeled available.
   Only an exact tested prompt, anchored elapsed reset and full revalidation can
   permit a bounded trial continuation; fresh contradictory quota still vetoes.
   Persist episode identity, attempt reservations and deadlines across changing
   screen fingerprints and rediscovery/restarts. Log session/provider/process,
   episode and attempt for all retry lifecycle events; update summary handling.
6. Use configurable `RETRY_SCHEDULE=1,2,3,5,8,13,21,34,55,89,600` by default for
   that Codex path. The first delay replaces reset grace there; subsequent delays
   begin after verification completes. No catch-up burst after suspend/restart.
   Stop on manual recovery, unsafe state, process replacement or exhausted budget;
   an explicitly later reset creates a new blocking episode.
7. Update AGENTS/vision/architecture/README to document the narrow safety-policy
   change authorized through debugging.md, without changing Claude's quota gate
   or allowing any paid, upgrade, reset-credit or model-changing choice.
8. Independently review the changes and adversarial/restart/revalidation tests;
   fix confirmed urgent/high issues and run the complete maturity pipeline,
   >=91% coverage gate, all safety simulations and read-only diagnostics.

No real terminal continuation, deployment, provider settings, push or release
is authorized by this implementation task. Leave the existing read-only
five-minute observation running; never manufacture live quota evidence.

## Completion evidence — v0.42.0 (2026-09-11)

- D1–D8 have regression coverage and fixes. The eleven-attempt simulation
  changes screen fingerprints, reloads persisted state, follows every backoff,
  and verifies that no twelfth continuation occurs, including after 24 hours.
- Independent review found and fixed a final-input revalidation gap, a
  reservation/action two-write crash gap, and cancelled checks consuming the
  typed-attempt budget. Clean pre-send cancellation now releases its reservation
  atomically; ambiguous sends and crash windows remain conservative.
- Claude's reported paid-offer identifier was also reproduced after the latest
  assistant turn marker. It no longer matches as a slash command; genuine paid
  commands and unsafe menu variants still veto input.
- `./localPipeline.sh` passed: REUSE, lint, formatting, ShellCheck, all safety
  simulations, profiling, source/wheel builds, the extracted source's quality
  gate outside Git, validated SPDX/CycloneDX SBOMs, and isolated installed-wheel
  diagnostics/simulations for both command names.
- 549 tests pass on each of Python 3.12, 3.13 and 3.14. The normally skipped
  opt-in Konsole integration test passes separately. Combined coverage is
  91.70% (statements 93.17%, branches 86.90%); the enforced combined floor is
  91%. This is not a claim that branch coverage exceeds 90% or every live
  behavior has been tested.
- Live doctor/status/quota diagnostics passed. Doctor correctly reports the
  existing controller's single-instance lock. No real continuation was sent,
  no running controller was replaced, and no provider setting was changed.
- The post-fix synthetic profile is recorded in `PERFORMANCE.md`.

Remaining operational limits: a clock-only prompt first seen after its reset,
without persisted or corroborating absolute-date evidence, cannot safely be
dated retroactively. Unsettled crash-window actions require manual inspection;
Konsole offers no atomic compare-screen-and-send operation. A natural live
quota-reset/resume cycle has not been exercised with this version. These local
commits have not been pushed, released or deployed, so hosted CI results and
the running controller do not yet attest to this version.
