<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Performance, verification and release metadata plan

## Objectives and boundaries

- Measure whole-app workload, including supervisor scans, quota/history reads,
  dashboard rendering and large retained-log summaries. Use synthetic data for
  reproducible profiles and read-only observe mode for live measurements.
- Fix measured significant waste without caching pre-input authorization or
  weakening identity, prompt, quota, policy or action-lifecycle checks.
- Raise combined statement/branch coverage above 90% through meaningful failure,
  integration and boundary tests; enforce at least 91% in the canonical gate.
- Add SPDX copyright/license annotations to every tracked file using native
  comments or sidecar metadata where embedded comments would break the format.
- Generate and validate SPDX and CycloneDX SBOMs for built release artifacts,
  explicitly documenting inventory scope and keeping runtime dependencies empty.

## Ordered work

1. Record baseline coverage and audit CI/release verification gaps. Commit this
   plan before implementation.
2. Add reproducible profiling and performance regression checks. Measure the
   current code, fix substantial bottlenecks, and record comparable results.
3. Close meaningful coverage gaps and strengthen test/CI gates: supported Python
   versions, installed package behavior, source packaging, and negative paths.
4. Add SPDX annotations plus automated completeness checks, preserving original
   license text and binary assets. Use REUSE-compatible metadata for exceptions.
5. Add validated SPDX/CycloneDX SBOM generation and publish the documents as
   quality/release artifacts. Audit build tooling and document remaining gaps.
6. Review all changes, run the full local pipeline and read-only live checks,
   record final coverage/performance evidence and limitations, and commit.

## Delivery

- Independent test and tooling tasks may use smaller-model workers; the main
  agent owns integration, performance decisions and final review.
- Keep logical changes in separate commits. Feature/fix commits bump the package
  version and add the matching newest changelog section.
- Run the repository's required lint/format/ShellCheck/pytest/diff checks before
  every commit. Do not lower coverage, remove difficult code from measurement,
  or add assertions that merely reproduce the implementation.
- No live continuation, provider setting change, deployment or new release is
  needed to validate this work. The genuine-reset acceptance gate remains a
  separate requirement; coverage and green CI are not proof of every live case.

## Completion evidence

Completed on 2026-09-10 for v0.41.0:

- Baseline: 424 passing tests, one opt-in live skip; combined coverage 89.29%.
  Final: 483 passing tests, one opt-in live skip; combined coverage 91.83%,
  statements 93.17%, branches 87.29%. The gate requires combined coverage >=91%;
  this is not a claim of >90% branch coverage or complete behavioral coverage.
- Deterministic profiles cover all safety simulations, four dashboard widths,
  Claude quota JSON, a 50,000-line Codex rollout, bounded history reads and a
  10,000-event operational summary. A representative one-iteration profile took
  0.625 seconds under cProfile: rendering 0.065s, quota/history 0.028s,
  simulations 0.016s, retained summary 0.516s. Summary processing remains linear
  in retained events and runs only on request, not in the dashboard scan loop.
- The amplified rendering benchmark improved from 12.890s to 0.626s. Twenty
  rapid scroll keys now cause one scan instead of 21. Explicit rescans, timeouts,
  pause/resume, interval and mode changes are tested independently.
- Current read-only live sample: 1.04s combined user/system CPU over 31.08s,
  36,096 KiB peak RSS. This is not a matched before/after desktop workload.
- Full canonical pipeline passes, including the freshly extracted source
  archive's quality gate, isolated installed-wheel commands without PYTHONPATH,
  both maintained SBOM validators and all 12 safety simulations.
- All 483 tests pass independently on Python 3.12, 3.13 and 3.14; the opt-in
  live test passes separately instead of remaining skipped on the KDE host.
- REUSE lint verifies repository and freshly built source-archive licensing.
  Native comments and sidecars preserve the original license and image bytes;
  narrowly scoped REUSE annotations cover generated packaging metadata.
- SPDX 2.3 and CycloneDX 1.6 documents inventory the runtime project and actual
  wheel/sdist hashes. Build/dev tools, Python and the operating system are
  explicitly outside that inventory. Unexpected runtime requirements are refused.
- Dependency advisory audit of the isolated developer environment, including
  the pinned build backend, found no known vulnerabilities at verification time.
- Independent review found no runtime safety regression. Fixed the source
  archive's omitted service-license sidecar, Git-only quality assumptions,
  shared-runner audit environment, and SBOM dependency-marker handling. Added
  tests rejecting corrupted SBOMs through the real standards validators.

## Remaining limits and maintenance

- Coverage does not prove every prompt or live race. Classification (73%) and
  the real Konsole adapter (78%) remain the lowest-covered runtime modules;
  future work should prioritize their OS/process failure branches over cosmetic
  percentage increases. No runtime code was excluded to meet the new floor.
- The opt-in live Konsole test and doctor/status/quota checks pass locally;
  the genuine provider-reset acceptance in [../OPEN_ISSUES.md](../OPEN_ISSUES.md)
  remains intentionally open.
- CI runs the canonical gate on Python 3.12/3.13/3.14, stores coverage/profile/
  SBOM artifacts, and publishes SBOMs on releases. Dependency auditing is a
  separate network-dependent push/PR/weekly job. New workflows require a push
  before their hosted results can be verified; this task does not push or tag.
- Synthetic timing reports are diagnostic, not portable latency guarantees.
  Operation-count and Unicode-layout tests are the deterministic regression gate.
