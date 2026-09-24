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
./localPipeline.sh
```

The gate provisions what it needs: when any pinned tool is missing it installs
the `dev` extra into `.venv` once and uses it, so a fresh clone runs its own
gate with no setup step. An environment that already has those tools, such as
CI after `pip install .[dev]`, is used unchanged. Set
`AGENT_WHILE_TRUE_TOOLCHAIN_VENV` to put that environment elsewhere.

Runtime code uses only the Python 3.12+ standard library; the `dev` extra pins
exact versions of the test, lint, build, licensing and SBOM tooling.

## The gate

`./localPipeline.sh` is the canonical release gate and the same script GitHub
Actions runs on Python 3.12, 3.13 and 3.14. It checks, in order:

1. Python 3.12+, and the pinned toolchain, provisioned if it is missing.
2. `scripts/quality.sh`: REUSE SPDX licensing, Ruff lint and format, ShellCheck
   on every tracked shell script, the worktree whitespace check, pytest with a
   98% combined statement/branch coverage floor, and version/changelog
   consistency.
3. Every built-in safety simulation (`simulate --all`).
4. A synthetic application profile, retained under `artifacts/`.
5. sdist and wheel construction; the wheel is built from the sdist.
6. The extracted source archive running its own quality gate outside Git.
7. SPDX 2.3 and CycloneDX 1.6 SBOM generation from the actual wheel and sdist,
   validated with maintained standards validators, retained in `dist/sbom/`.
8. The wheel installed into a fresh virtual environment, with `PYTHONPATH`
   removed, exercising `--version`, `doctor`, `status`, `quota`, `summary` and
   `simulate --all`.

### Coverage

The floor is 98% of statements and branches combined, measured over
`src/agent_while_true` by `scripts/quality.sh`; 0.50.8 measured 98.7%. It is a
floor for behaviour, not for lines:

- Cover a branch with a test that states what the branch is for - a refusal, a
  fail-closed read, a degraded diagnostic - not with a call that merely
  executes it. Fake-terminal, fake-`/proc` and stand-in-executable tests are
  the norm; nothing may send input to a real session or depend on the host.
- Delete a branch that cannot run instead of excluding it. `# pragma: no cover`
  is reserved for code that is reachable only outside a test process (signal
  handlers, `__main__`) or defensively unreachable by construction, with the
  reason written beside it.
- `Protocol` classes are excluded in `pyproject.toml`: a structural interface
  has no behaviour of its own.

Run `.venv/bin/python -m pytest --cov=agent_while_true
--cov-report=term-missing:skip-covered` to see what a change left uncovered.

The faster inner loop is the required pre-commit set from AGENTS.md:

```bash
ruff check . && ruff format --check . && shellcheck --severity=style scripts/*.sh
python3 -m pytest -q
git --no-pager diff --check
```

`--no-pager` matters in a script: Git pages `diff` output, and a `LESS` value
without `-F` then holds an automated run open on an empty diff.

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

Every versioned commit bumps `__version__` and opens the matching newest
`CHANGELOG.md` section. `scripts/bump_version.py` makes both edits together,
reading the section body from standard input:

```bash
printf -- '- Describe the change.\n' | scripts/bump_version.py 0.50.10 Fixed
```

It refuses a version that is not newer, an unknown Keep a Changelog category
and an empty body, and writes nothing when it refuses.
