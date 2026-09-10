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
