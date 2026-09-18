<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Development and release engineering

How the quality gate, CI, packaging and release artifacts work. The contributor
rules — one logical change per commit, version and changelog bumps, the release
procedure and the safety invariants — are in [AGENTS.md](../AGENTS.md).

## Set up a checkout

```bash
git clone https://github.com/marcelpetrick/AgentWhileTrue.git
cd AgentWhileTrue
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PATH="$PWD/.venv/bin:$PATH" ./localPipeline.sh
```

Runtime code uses only the Python 3.12+ standard library; the `dev` extra pins
exact versions of the test, lint, build, licensing and SBOM tooling.

## The gate

`./localPipeline.sh` is the canonical release gate and the same script GitHub
Actions runs on Python 3.12, 3.13 and 3.14. It checks, in order:

1. Python 3.12+.
2. `scripts/quality.sh`: REUSE SPDX licensing, Ruff lint and format, ShellCheck
   on every tracked shell script, `git diff --check`, pytest with a 91%
   combined statement/branch coverage floor, and version/changelog consistency.
3. Every built-in safety simulation (`simulate --all`).
4. A synthetic application profile, retained under `artifacts/`.
5. sdist and wheel construction; the wheel is built from the sdist.
6. The extracted source archive running its own quality gate outside Git.
7. SPDX 2.3 and CycloneDX 1.6 SBOM generation from the actual wheel and sdist,
   validated with maintained standards validators, retained in `dist/sbom/`.
8. The wheel installed into a fresh virtual environment, with `PYTHONPATH`
   removed, exercising `--version`, `doctor`, `status`, `quota`, `summary` and
   `simulate --all`.

The faster inner loop is the required pre-commit set from AGENTS.md:

```bash
ruff check . && ruff format --check . && shellcheck --severity=style scripts/*.sh
python3 -m pytest -q
git diff --check
```

The opt-in live adapter test needs a running KDE Konsole and only reads:

```bash
AGENT_WHILE_TRUE_LIVE_KONSOLE=1 python3 -m pytest -q -m konsole
```

Deterministic operation-count tests guard performance without machine-speed
thresholds; measured timings and workloads are in
[PERFORMANCE.md](PERFORMANCE.md).

## Licensing and SBOMs

All tracked files carry SPDX metadata through native comments or `.license`
sidecars, checked by `reuse lint`; new files must do the same. The SBOMs
describe the project, its empty third-party runtime dependency graph and the
release-artifact checksums — not the OS, interpreter or build environment.
An unexpected runtime dependency fails generation until inventory support is
added.

The online dependency advisory check is separate from the offline-capable gate:

```bash
python3 -m pip_audit --progress-spinner off
```

## Continuous integration

| Workflow | Trigger | Does |
| --- | --- | --- |
| `quality.yml` | push/PR to `master` | `./localPipeline.sh --noRun` on 3.12/3.13/3.14; uploads dist, coverage and profile |
| `security.yml` | push/PR, weekly | `pip-audit` over the installed development/build tooling |
| `release.yml` | tag `agentwhiletrue-vX.Y.Z` | verifies tag = `__version__` = newest changelog entry, reruns the pipeline, publishes wheel, sdist and SBOMs as a GitHub release |

## Versioning

`src/agent_while_true/version.py` is the single source of truth; `pyproject`
reads it and the gate asserts the newest `CHANGELOG.md` heading matches. The
project follows semantic versioning; while the major version is `0`, the minor
version bumps for features and the patch version for fixes. Intermediate
versioned commits are normal development versions — a tag is cut only for a
fully verified release, and the README install command is pointed at that tag.
