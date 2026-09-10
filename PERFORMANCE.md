<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Performance evaluation

This document records measured idle workload on the primary development
machine. It is evidence for the default architecture, not a universal benchmark:
terminal count, provider latency, kernel caches, and Konsole versions affect the
result.

## Test environment

Measured on 2026-09-09 with:

- Manjaro Linux 7.1.13, KDE Plasma on Wayland, and KDE Konsole;
- Python 3.14.7;
- seven to eight visible Konsole sessions, including five selected Codex or
  Claude sessions;
- the default 2-second selected-session scan interval;
- the required 1-second provider-health interval;
- no configured HTTP or HTTPS proxy, so the persistent direct transport was
  active;
- observe mode, `--all`, `--no-fzf`, and `--no-color`;
- output redirected to `/dev/null` so terminal rendering did not dominate the
  process measurement.

Observe mode was used throughout and no terminal input was sent.

## Method

CPU, memory, page faults, and context switches were captured with GNU `time`:

```bash
/usr/bin/time -v timeout --signal=TERM --kill-after=5s 30s \
  env PYTHONPATH=src python3 -m agent_watch.cli run \
  --observe --all --no-fzf --no-color >/dev/null
```

External process calls were counted separately with `strace` over ten seconds:

```bash
strace -f -qq -c -e trace=process \
  timeout --signal=TERM --kill-after=5s 10s \
  env PYTHONPATH=src python3 -m agent_watch.cli run \
  --observe --all --no-fzf --no-color >/dev/null
```

The before measurement used one new HTTPS connection per provider check and
full Konsole rediscovery on every dashboard scan. The after measurement reused
one HTTPS connection per provider, rediscovered all Konsole sessions every 30
seconds, and continued scanning selected sessions every two seconds. Manual `r`
still causes immediate rediscovery, and every proposed action still performs
fresh identity, process, prompt, quota, and policy checks.

## Results

| Metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| Elapsed sample | 31.53 s | 30.78 s | comparable |
| User CPU | 3.06 s | 0.49 s | -84.0% |
| System CPU | 2.02 s | 0.25 s | -87.6% |
| Total CPU time | 5.08 s | 0.74 s | -85.4% |
| Reported share of one CPU core | 16% | 2% | -87.5% |
| Maximum resident set | 36,220 KiB | 35,288 KiB | -2.6% |
| Voluntary context switches | 33,913 | 2,607 | -92.3% |
| Involuntary context switches | 2,949 | 453 | -84.6% |
| Successful process executions per 10 s | 180 | 40 | -77.8% |

The after result averages about 25 milliseconds of CPU time per wall-clock
second and approximately 34.5 MiB peak resident memory. The remaining external
process work is primarily the conservative `qdbus` inspection of selected
Konsole sessions.

## Provider-health traffic

A separate ten-check live sample reused the same two persistent HTTPS
connections as the implementation:

| Provider | Checks | HTTP results | Compressed response bodies |
| --- | ---: | --- | ---: |
| OpenAI | 10 | ten `200` responses | 11,480 bytes |
| Anthropic | 10 | two `200`, eight `304` responses | 1,264 bytes |
| Total | 20 | two checks per second | 12,744 bytes |

This is about 1.27 KB of compressed response bodies per second across both
providers. HTTP headers and the initial DNS/TCP/TLS setup are not included in
that body count. On the measured direct path, connections stay open between
checks, response bodies are bounded to 128 KiB compressed and decompressed, and
transport failure closes the connection so the next check reconnects cleanly.
When an HTTP(S) proxy is configured, Agent While True preserves the
standard-library proxy-aware transport instead; its CPU and traffic
characteristics were not measured here. Unknown or failed responses remain
`UNKNOWN`; connection reuse does not reuse authorization decisions.

## Evaluation

The original behavior was too expensive for an idle supervisor. Repeating full
Konsole discovery and TLS setup on every short interval created avoidable CPU,
process, and scheduler load.

The revised behavior meets the intended balance on this machine:

- official provider outage state is still checked once per second;
- selected terminal sessions are still inspected every two seconds by default;
- new or removed Konsole sessions settle within 30 seconds, or immediately when
  the user presses `r`;
- CPU demand is low single-digit usage of one core rather than sustained
  double-digit usage;
- memory remains stable and modest for a Python TUI;
- all safety-critical pre-action reads remain immediate and uncached.

Workload scales mainly with the number of selected sessions because the Konsole
adapter intentionally uses scoped D-Bus calls for each live identity and screen.
Users supervising unusually many sessions can increase the selected-session
interval with `+` or `--scan-interval`; the one-second provider-health floor is
independent of that setting.

Re-run this profile after changes to terminal discovery, quota polling, status
transport, dashboard cadence, or process inspection. Compare like-for-like
session counts and record both CPU time and subprocess activity; elapsed time or
network body size alone can hide a regression.

## Deterministic application profile

The repository also includes a synthetic `cProfile` workload. It exercises all
fake-terminal safety simulations, narrow and wide dashboard rendering, Claude
quota parsing, a 50,000-line Codex rollout tail, bounded reads from a
10,000-entry event log, and its retained operational summary:

```bash
python3 scripts/profile_app.py --iterations 5 --profile artifacts/profile.prof
python3 -m pstats artifacts/profile.prof
```

The tool creates the profile's parent directory. It uses temporary synthetic
data exclusively and reports timings and function names, never terminal text,
environment values, or credentials. Running it as root does not enable live
inspection or input.

On 2026-09-10 with Python 3.14.7, the measured rendering bottleneck was
reproduced with `--iterations 1 --render-frames 300 --render-width 100`.
Before optimization, the 300 frames took 12.890 seconds and 52,845,302 calls:
`_wrap` accounted for 8.773 seconds cumulative, `_cell_width` for 6.438 seconds,
and the Unicode database functions were each called over ten million times.
After adding ASCII fast paths, the same 300 frames took 0.626 seconds and
1,746,002 calls, about 20.6 times faster. Unicode text retains the width-aware
path. Regression tests use semantic operation counts rather than fragile timing
thresholds: ASCII layout must make zero Unicode database lookups, while wide
and combining characters must retain their original layout.

A separate read-only live observe sample after the change used the existing
GNU `time` command above for 30 seconds and measured 0.64 seconds user CPU,
0.40 seconds system CPU, 31.08 seconds elapsed, and 36,096 KiB maximum RSS.
That is about 3.35% of one CPU including startup, shutdown, and subprocesses.
No terminal input was sent. Session counts differed from the earlier sample,
so this result is current evidence rather than a like-for-like comparison.
