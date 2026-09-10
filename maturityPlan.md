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

To be filled with measured baseline/final coverage, profile results, CI gates,
SBOM scope/validation, review findings and remaining operational acceptance work.
