#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later

"""Metadata-only quota benchmark, using invented files in an isolated tempdir.

Use the same interpreter/workload before and after a change. Never instantiates
a writable supervisor or sends input. ``--live-scans`` additionally measures
read-only observations with real process-bound quota. Output contains only
counts/timings, never terminal titles, screens or account data. Temporary quota
files are invented; live screens remain in memory and are immediately discarded.
"""

import argparse
import json
import statistics
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agent_while_true import quota
from agent_while_true.version import __version__


def bounded_int(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 10000:
        raise argparse.ArgumentTypeError("expected an integer from 1 to 10000")
    return number


def quota_benchmark(rounds: int, archived: int) -> dict[str, object]:
    """Measure four sessions, each warmed/read once, as in a normal scan."""
    now = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="awt-quota-benchmark-") as temporary:
        directory = Path(temporary)
        for index in range(archived + 4):
            document = {
                "source": "claude",
                "updated_at": now.isoformat(),
                "process": {"pid": 10000 + index, "start_time": 20000 + index},
                "five_hour": {
                    "used_percentage": 25,
                    "resets_at": (now + timedelta(hours=4)).isoformat(),
                },
            }
            (directory / f"claude-{index:05d}.json").write_text(json.dumps(document))
        source = quota.ClaudeStatuslineSource(directory / "claude.json")
        original_loads = json.loads
        parses = 0

        def counted_loads(*args, **kwargs):
            nonlocal parses
            parses += 1
            return original_loads(*args, **kwargs)

        durations = []
        parse_counts = []
        with (
            patch.object(quota, "read_start_time", new=lambda pid: pid + 10000),
            patch.object(quota.json, "loads", new=counted_loads),
        ):
            for _ in range(rounds + 1):
                previous = parses
                start = time.perf_counter()
                for _pass in range(2):
                    for pid in range(10000, 10004):
                        result = source.snapshot(pid=pid)
                        if result.availability is not quota.Availability.AVAILABLE:
                            raise RuntimeError("synthetic quota did not remain available")
                durations.append((time.perf_counter() - start) * 1000)
                parse_counts.append(parses - previous)
        return {
            "files": archived + 4,
            "sessions": 4,
            "snapshots_per_scan": 8,
            "rounds": rounds,
            "cold_ms": round(durations[0], 3),
            "warm_median_ms": round(statistics.median(durations[1:]), 3),
            "warm_min_ms": round(min(durations[1:]), 3),
            "warm_max_ms": round(max(durations[1:]), 3),
            "cold_json_parses": parse_counts[0],
            "warm_json_parses_per_scan": parse_counts[1:],
        }


def live_scan_benchmark(rounds: int) -> dict[str, object]:
    """Observe only: never call tick/act/approve, persist state or send input."""
    from agent_while_true.config import Config, Mode, default_state_dir
    from agent_while_true.fsm import SupervisedSession, Supervisor, SystemInspector
    from agent_while_true.picker import discover
    from agent_while_true.state_store import StateStore
    from agent_while_true.terminal.konsole import KonsoleAdapter

    terminal = KonsoleAdapter()
    inspector = SystemInspector()
    with tempfile.TemporaryDirectory(prefix="awt-readonly-benchmark-") as temporary:
        supervisor = Supervisor(
            terminal=terminal,
            config=Config(mode=Mode.OBSERVE),
            inspector=inspector,
            store=StateStore.in_directory(Path(temporary)),
            quota_sources=quota.default_sources(default_state_dir()),
        )
        for candidate in discover(terminal, inspector):
            if candidate.eligible and candidate.info is not None and candidate.provider is not None:
                supervisor.sessions[candidate.key] = SupervisedSession(
                    ref=candidate.session.ref,
                    identity=candidate.info.identity,
                    provider_name=candidate.provider,
                    title="",
                )
        durations = []
        for _ in range(rounds + 1):
            start = time.perf_counter()
            supervisor._warm_quota_sources()
            for session in supervisor.sessions.values():
                supervisor.observe(session.ref)
            durations.append((time.perf_counter() - start) * 1000)
        return {
            "sessions": len(supervisor.sessions),
            "rounds": rounds,
            "cold_ms": round(durations[0], 3),
            "warm_median_ms": round(statistics.median(durations[1:]), 3),
            "warm_min_ms": round(min(durations[1:]), 3),
            "warm_max_ms": round(max(durations[1:]), 3),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=bounded_int, default=7)
    parser.add_argument("--archived", type=bounded_int, default=250)
    parser.add_argument(
        "--live-scans", action="store_true", help="also observe live agents read-only"
    )
    args = parser.parse_args()
    report = {"version": __version__, "quota": quota_benchmark(args.rounds, args.archived)}
    if args.live_scans:
        report["live_scans"] = live_scan_benchmark(args.rounds)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
