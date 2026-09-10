<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Live acceptance checklist

Repository implementation, automated verification, packaging, deployment, and
release are complete. This checklist stays open because its final evidence must
come from a naturally occurring provider quota reset in a real Konsole session.

## Verified environment — 2026-09-09

- [x] Manjaro Linux, KDE Plasma, Wayland, and current Konsole detected.
- [x] `doctor` reports `Konsole input OK` and `Auto mode OK`.
- [x] Live session discovery identifies Codex through its Node launcher and
  identifies Claude Code directly.
- [x] Codex rollout and Claude status-line quota sources report account-bound
  five-hour and weekly windows.
- [x] Observe mode and every dashboard control were exercised without terminal
  input.
- [x] The opt-in live Konsole adapter test passed using its empty scoped probe.
- [x] The event log was checked for prompt, credential, and environment content.
- [x] Built-in reset, stale-state, provider-failure, PID-reuse, crash-recovery,
  duplicate-prompt, Codex-opt-in, and observe-mode simulations pass.
- [x] The installed wheel passes `--version`, `doctor`, `quota`, `status`, and
  `simulate --all`; the `agent-watch` compatibility command also works.

## Remaining real-reset validation

- [ ] Run the current release in full-auto mode for the intended sessions.
- [ ] Observe a supported session reach a genuine quota limit and later become
  eligible without replacing its process or altering provider evidence.
- [ ] Confirm Agent While True sends exactly one permitted continuation after
  the configured reset grace period.
- [ ] Inspect the last 50 structured events:

  ```bash
  agent-while-true logs -n 50
  ```

- [ ] Confirm the action records `PLANNED`, `SENT`, and `VERIFIED`, or an honest
  `FAILED` result with no unsafe retry.
- [ ] Reconfirm that history contains no terminal text, prompt content,
  credentials, tokens, emails, or environment values.

## Constraints

- Do not manufacture availability, edit quota files, or use stale data to close
  this gate.
- Do not select a paid, upgrade, reset-credit, or model-changing option as a
  test.
- Do not send input to unrelated live sessions.
- A refusal caused by unknown, stale, malformed, or conflicting evidence is a
  correct result, but it does not complete the eligible-reset validation.

Acceptance is complete only after one genuine eligible reset continues exactly
once and its privacy-preserving persisted lifecycle is verified.
